# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime

from odoo import fields, models, _
from odoo.exceptions import UserError

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
except Exception:  # pragma: no cover
    Workbook = None


class StockPeriodReportWizard(models.TransientModel):
    _name = "stock.period.report.wizard"
    _description = "Stock Movement Between Dates Wizard"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    date_from = fields.Datetime(
        string="Date From",
        required=True,
        default=lambda self: fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
    )
    date_to = fields.Datetime(string="Date To", required=True, default=lambda self: fields.Datetime.now())

    warehouse_id = fields.Many2one("stock.warehouse", domain="[('company_id', '=', company_id)]")
    location_ids = fields.Many2many(
        "stock.location",
        "stock_period_report_location_rel",
        "wizard_id",
        "location_id",
        string="Locations",
        domain="[('usage', 'in', ('internal', 'transit')), ('company_id', 'in', (False, company_id))]",
        help="If empty, all internal/transit locations of the selected warehouse (or company) will be used.",
    )

    product_ids = fields.Many2many("product.product", string="Products")
    categ_id = fields.Many2one("product.category", string="Product Category")

    show_value = fields.Boolean(
        string="Show Value",
        default=True,
        help="Best effort valuation using stock valuation layers (company-wide).",
    )

    report_mode = fields.Selection(
        [
            ("detailed", "تفاصيل الحركات"),
            ("product", "ملخص حسب الصنف"),
            ("product_location", "ملخص حسب الصنف والموقع"),
        ],
        default="detailed",
        required=True,
    )

    line_ids = fields.One2many("stock.period.report.line", "wizard_id", string="Lines", readonly=True)

    xlsx_file = fields.Binary(string="Excel File", readonly=True, attachment=False)
    xlsx_filename = fields.Char(string="Excel Filename", readonly=True)

    def _get_effective_locations(self):
        self.ensure_one()
        if self.location_ids:
            return self.location_ids

        if self.warehouse_id and self.warehouse_id.view_location_id:
            return self.env["stock.location"].search(
                [
                    ("id", "child_of", self.warehouse_id.view_location_id.id),
                    ("usage", "in", ("internal", "transit")),
                    ("company_id", "in", (False, self.company_id.id)),
                ]
            )

        return self.env["stock.location"].search(
            [
                ("usage", "in", ("internal", "transit")),
                ("company_id", "in", (False, self.company_id.id)),
            ]
        )

    def _get_products(self):
        self.ensure_one()
        domain = [("type", "=", "product")]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.categ_id:
            domain.append(("categ_id", "child_of", self.categ_id.id))
        return self.env["product.product"].search(domain)

    def _spr_get_param(self, key, default):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)
    
    def _spr_labels(self):
        return {
            "opening": self._spr_get_param("spr.label_opening", "الرصيد الافتتاحي"),
            "closing": self._spr_get_param("spr.label_closing", "الرصيد الختامي"),
            "in": self._spr_get_param("spr.label_in", "وارد"),
            "out": self._spr_get_param("spr.label_out", "صادر"),
            "internal": self._spr_get_param("spr.label_internal", "تحويل داخلي"),
            "xlsx_title": self._spr_get_param("spr.xlsx_title", "تقرير حركة المخزون بين فترتين"),
        }

    def action_generate(self):
        self.ensure_one()

        if self.date_to < self.date_from:
            raise UserError(_("Date To must be after Date From."))

        self.xlsx_file = False
        self.xlsx_filename = False
        self.line_ids.unlink()

        locs = self._get_effective_locations()
        if not locs:
            raise UserError(_("No locations found for the selected criteria."))

        products = self._get_products()
        if not products:
            raise UserError(_("No products found for the selected criteria."))

        if self.report_mode == "detailed":
            opening_qty_map = self._compute_opening_qty_net(products, locs)
            self._generate_detailed(products, opening_qty_map, locs)
        elif self.report_mode == "product":
            opening_qty_map = self._compute_opening_qty_net(products, locs)
            self._generate_product_summary(products, opening_qty_map, locs)
        else:
            opening_map = self._compute_opening_qty_by_location(products, locs)
            self._generate_product_location_summary(products, opening_map, locs)

        action = self.env.ref("stock_period_movement_report.action_stock_period_report_lines").read()[0]
        action["domain"] = [("wizard_id", "=", self.id)]
        return action

    # -----------------------------
    # Opening calculations
    # -----------------------------
    def _compute_opening_qty_net(self, products, locs):
        """Net opening per product for selected locations as one bucket."""
        self.ensure_one()
        cr = self.env.cr
        loc_ids = tuple(locs.ids) or (0,)
        prod_ids = tuple(products.ids) or (0,)

        # In: dest in locs AND source not in locs
        cr.execute(
            """
            SELECT sml.product_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date < %s
               AND sml.product_id IN %s
               AND sml.location_dest_id IN %s
               AND sml.location_id NOT IN %s
             GROUP BY sml.product_id
            """,
            (self.company_id.id, self.date_from, prod_ids, loc_ids, loc_ids),
        )
        in_map = {pid: qty for pid, qty in cr.fetchall()}

        # Out: source in locs AND dest not in locs
        cr.execute(
            """
            SELECT sml.product_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date < %s
               AND sml.product_id IN %s
               AND sml.location_id IN %s
               AND sml.location_dest_id NOT IN %s
             GROUP BY sml.product_id
            """,
            (self.company_id.id, self.date_from, prod_ids, loc_ids, loc_ids),
        )
        out_map = {pid: qty for pid, qty in cr.fetchall()}

        return {p.id: float(in_map.get(p.id, 0.0) - out_map.get(p.id, 0.0)) for p in products}

    def _compute_opening_qty_by_location(self, products, locs):
        """Opening per (product, location). Counts transfers between selected locations correctly."""
        self.ensure_one()
        cr = self.env.cr
        loc_ids = tuple(locs.ids) or (0,)
        prod_ids = tuple(products.ids) or (0,)

        # In per dest location: dest = loc, source != loc
        cr.execute(
            """
            SELECT sml.product_id, sml.location_dest_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date < %s
               AND sml.product_id IN %s
               AND sml.location_dest_id IN %s
               AND sml.location_id != sml.location_dest_id
             GROUP BY sml.product_id, sml.location_dest_id
            """,
            (self.company_id.id, self.date_from, prod_ids, loc_ids),
        )
        in_map = {(pid, loc): qty for pid, loc, qty in cr.fetchall()}

        # Out per source location: source = loc, dest != loc
        cr.execute(
            """
            SELECT sml.product_id, sml.location_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date < %s
               AND sml.product_id IN %s
               AND sml.location_id IN %s
               AND sml.location_id != sml.location_dest_id
             GROUP BY sml.product_id, sml.location_id
            """,
            (self.company_id.id, self.date_from, prod_ids, loc_ids),
        )
        out_map = {(pid, loc): qty for pid, loc, qty in cr.fetchall()}

        opening = {}
        for p in products:
            for loc in locs:
                opening[(p.id, loc.id)] = float(in_map.get((p.id, loc.id), 0.0) - out_map.get((p.id, loc.id), 0.0))
        return opening

    # -----------------------------
    # Valuation helpers (best effort)
    # -----------------------------
    def _avg_cost_before(self, product, dt):
        self.ensure_one()
        SVL = self.env["stock.valuation.layer"].sudo()
        layers = SVL.search(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "=", product.id),
                ("create_date", "<", dt),
            ]
        )
        qty = 0.0
        val = 0.0
        for l in layers:
            qty += l.quantity or 0.0
            val += l.value or 0.0
        if qty:
            return val / qty
        return product.standard_price

    def _unit_cost_from_move(self, move):
        self.ensure_one()
        SVL = self.env["stock.valuation.layer"].sudo()
        layers = SVL.search(
            [
                ("company_id", "=", self.company_id.id),
                ("stock_move_id", "=", move.id),
            ],
            limit=50,
        )
        total_qty = 0.0
        total_val = 0.0
        for l in layers:
            if not l.quantity:
                continue
            total_qty += l.quantity
            total_val += l.value
        if total_qty:
            return abs(total_val / total_qty)
        return move.product_id.standard_price

    # -----------------------------
    # Detailed movements
    # -----------------------------
    def _movement_type_net(self, move_line, loc_ids_set):
        src_in = move_line.location_id.id in loc_ids_set
        dst_in = move_line.location_dest_id.id in loc_ids_set
        if dst_in and not src_in:
            return "IN"
        if src_in and not dst_in:
            return "OUT"
        if src_in and dst_in:
            return "INT"
        return "OTHER"

    def _generate_detailed(self, products, opening_qty_map, locs):
        self.ensure_one()
        labels = self._spr_labels()
        Line = self.env["stock.period.report.line"]
        loc_ids_set = set(locs.ids)

        domain = [
            ("move_id.state", "=", "done"),
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("product_id", "in", products.ids),
            "|",
            ("location_id", "in", locs.ids),
            ("location_dest_id", "in", locs.ids),
        ]
        smls = self.env["stock.move.line"].search(domain, order="product_id, date, id")

        balance_qty = {p.id: opening_qty_map.get(p.id, 0.0) for p in products}
        balance_val = {}

        # Opening lines per product
        for p in products:
            if self.show_value:
                avg_cost = self._avg_cost_before(p, self.date_from)
                balance_val[p.id] = balance_qty[p.id] * avg_cost
            else:
                balance_val[p.id] = 0.0

            Line.create(
                {
                    "wizard_id": self.id,
                    "is_opening": True,
                    "date": self.date_from,
                    "product_id": p.id,
                    "reference": labels["opening"],
                    "movement_type": "OPEN",
                    "qty_in": 0.0,
                    "qty_out": 0.0,
                    "balance_qty": balance_qty[p.id],
                    "unit_cost": (balance_val[p.id] / balance_qty[p.id]) if (self.show_value and balance_qty[p.id]) else 0.0,
                    "movement_value": 0.0,
                    "balance_value": balance_val[p.id] if self.show_value else 0.0,
                }
            )

        for ml in smls:
            mtype = self._movement_type_net(ml, loc_ids_set)
            if mtype == "OTHER":
                continue

            qty_in = qty_out = 0.0
            if mtype == "IN":
                qty_in = ml.quantity
            elif mtype == "OUT":
                qty_out = ml.quantity
            else:  # INT net zero
                qty_in = ml.quantity
                qty_out = ml.quantity

            pid = ml.product_id.id
            balance_qty[pid] = balance_qty.get(pid, 0.0) + qty_in - qty_out

            unit_cost = self._unit_cost_from_move(ml.move_id) if self.show_value else 0.0
            move_val = (qty_in - qty_out) * unit_cost
            balance_val[pid] = balance_val.get(pid, 0.0) + move_val

            Line.create(
                {
                    "wizard_id": self.id,
                    "date": ml.date,
                    "product_id": pid,
                    "reference": ml.reference
                    or ml.move_id.reference
                    or ml.move_id.origin
                    or (ml.picking_id.name if ml.picking_id else "")
                    or "",
                    "picking_id": ml.picking_id.id if ml.picking_id else False,
                    "move_id": ml.move_id.id,
                    "movement_type": mtype,
                    "location_id": ml.location_id.id,
                    "location_dest_id": ml.location_dest_id.id,
                    "qty_in": qty_in,
                    "qty_out": qty_out,
                    "balance_qty": balance_qty[pid],
                    "unit_cost": unit_cost,
                    "movement_value": move_val if self.show_value else 0.0,
                    "balance_value": balance_val[pid] if self.show_value else 0.0,
                }
            )

        for p in products:
            Line.create(
                {
                    "wizard_id": self.id,
                    "is_closing": True,
                    "date": self.date_to,
                    "product_id": p.id,
                    "reference": labels["closing"],
                    "movement_type": "CLOSE",
                    "qty_in": 0.0,
                    "qty_out": 0.0,
                    "balance_qty": balance_qty.get(p.id, 0.0),
                    "unit_cost": (balance_val.get(p.id, 0.0) / balance_qty.get(p.id, 0.0)) if (self.show_value and balance_qty.get(p.id, 0.0)) else 0.0,
                    "movement_value": 0.0,
                    "balance_value": balance_val.get(p.id, 0.0) if self.show_value else 0.0,
                }
            )

    # -----------------------------
    # Summaries
    # -----------------------------
    def _generate_product_summary(self, products, opening_qty_map, locs):
        self.ensure_one()
        labels = self._spr_labels()
        Line = self.env["stock.period.report.line"]
        cr = self.env.cr
        loc_ids = tuple(locs.ids) or (0,)
        prod_ids = tuple(products.ids) or (0,)

        # In within period
        cr.execute(
            """
            SELECT sml.product_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date >= %s AND sml.date <= %s
               AND sml.product_id IN %s
               AND sml.location_dest_id IN %s
               AND sml.location_id NOT IN %s
             GROUP BY sml.product_id
            """,
            (self.company_id.id, self.date_from, self.date_to, prod_ids, loc_ids, loc_ids),
        )
        in_map = {pid: qty for pid, qty in cr.fetchall()}

        # Out within period
        cr.execute(
            """
            SELECT sml.product_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date >= %s AND sml.date <= %s
               AND sml.product_id IN %s
               AND sml.location_id IN %s
               AND sml.location_dest_id NOT IN %s
             GROUP BY sml.product_id
            """,
            (self.company_id.id, self.date_from, self.date_to, prod_ids, loc_ids, loc_ids),
        )
        out_map = {pid: qty for pid, qty in cr.fetchall()}

        for p in products:
            opening_qty = float(opening_qty_map.get(p.id, 0.0))
            in_qty = float(in_map.get(p.id, 0.0))
            out_qty = float(out_map.get(p.id, 0.0))
            closing_qty = opening_qty + in_qty - out_qty

            unit_cost = 0.0
            opening_val = movement_val = closing_val = 0.0
            if self.show_value:
                unit_cost = self._avg_cost_before(p, self.date_from)
                opening_val = opening_qty * unit_cost
                movement_val = (in_qty - out_qty) * unit_cost
                closing_val = opening_val + movement_val

            Line.create(
                {
                    "wizard_id": self.id,
                    "date": self.date_to,
                    "product_id": p.id,
                    "reference": "ملخص حسب الصنف",
                    "movement_type": "SUM",
                    "qty_opening": opening_qty,
                    "qty_in": in_qty,
                    "qty_out": out_qty,
                    "balance_qty": closing_qty,
                    "unit_cost": unit_cost,
                    "opening_value": opening_val if self.show_value else 0.0,
                    "movement_value": movement_val if self.show_value else 0.0,
                    "balance_value": closing_val if self.show_value else 0.0,
                }
            )

    def _generate_product_location_summary(self, products, opening_map, locs):
        self.ensure_one()
        labels = self._spr_labels()
        Line = self.env["stock.period.report.line"]
        cr = self.env.cr

        loc_ids = tuple(locs.ids) or (0,)
        prod_ids = tuple(products.ids) or (0,)

        # In per location (dest)
        cr.execute(
            """
            SELECT sml.product_id, sml.location_dest_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date >= %s AND sml.date <= %s
               AND sml.product_id IN %s
               AND sml.location_dest_id IN %s
               AND sml.location_id != sml.location_dest_id
             GROUP BY sml.product_id, sml.location_dest_id
            """,
            (self.company_id.id, self.date_from, self.date_to, prod_ids, loc_ids),
        )
        in_map = {(pid, loc): qty for pid, loc, qty in cr.fetchall()}

        # Out per location (source)
        cr.execute(
            """
            SELECT sml.product_id, sml.location_id, COALESCE(SUM(sml.quantity), 0.0) AS qty
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
             WHERE sm.state = 'done'
               AND sm.company_id = %s
               AND sml.date >= %s AND sml.date <= %s
               AND sml.product_id IN %s
               AND sml.location_id IN %s
               AND sml.location_id != sml.location_dest_id
             GROUP BY sml.product_id, sml.location_id
            """,
            (self.company_id.id, self.date_from, self.date_to, prod_ids, loc_ids),
        )
        out_map = {(pid, loc): qty for pid, loc, qty in cr.fetchall()}

        for p in products:
            unit_cost = self._avg_cost_before(p, self.date_from) if self.show_value else 0.0
            for loc in locs:
                opening_qty = float(opening_map.get((p.id, loc.id), 0.0))
                in_qty = float(in_map.get((p.id, loc.id), 0.0))
                out_qty = float(out_map.get((p.id, loc.id), 0.0))
                closing_qty = opening_qty + in_qty - out_qty

                opening_val = movement_val = closing_val = 0.0
                if self.show_value:
                    opening_val = opening_qty * unit_cost
                    movement_val = (in_qty - out_qty) * unit_cost
                    closing_val = opening_val + movement_val

                Line.create(
                    {
                        "wizard_id": self.id,
                        "date": self.date_to,
                        "product_id": p.id,
                        "location_id": loc.id,
                        "reference": "ملخص حسب الصنف والموقع",
                        "movement_type": "SUMLOC",
                        "qty_opening": opening_qty,
                        "qty_in": in_qty,
                        "qty_out": out_qty,
                        "balance_qty": closing_qty,
                        "unit_cost": unit_cost,
                        "opening_value": opening_val if self.show_value else 0.0,
                        "movement_value": movement_val if self.show_value else 0.0,
                        "balance_value": closing_val if self.show_value else 0.0,
                    }
                )

    # -----------------------------
    # Excel export
    # -----------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        self = self.sudo()
        if Workbook is None:
            raise UserError(_("openpyxl is not available on the server."))

        if not self.line_ids:
            # generate first
            self.action_generate()

        wb = Workbook()
        ws = wb.active
        ws.title = "التقرير"

        headers = [
            "الصنف",
            "التاريخ",
            "نوع الحركة",
            "المرجع",
            "من",
            "إلى",
            "الرصيد الافتتاحي (كمية)",
            "الكمية الداخلة",
            "الكمية الخارجة",
            "الرصيد (كمية)",
            "تكلفة الوحدة",
            "الرصيد الافتتاحي (قيمة)",
            "قيمة الحركة",
            "الرصيد (قيمة)",
        ]
        ws.append(headers)

        def dt(v):
            if not v:
                return ""
            # keep in user timezone in UI; for excel just string
            return fields.Datetime.to_string(v)

        for l in self.line_ids.sorted(lambda x: (x.product_id.id, x.date or fields.Datetime.now(), x.id)):
            ws.append(
                [
                    l.product_id.display_name,
                    dt(l.date),
                    l.movement_type,
                    l.reference or "",
                    l.location_id.display_name if l.location_id else "",
                    l.location_dest_id.display_name if l.location_dest_id else "",
                    l.qty_opening or 0.0,
                    l.qty_in or 0.0,
                    l.qty_out or 0.0,
                    l.balance_qty or 0.0,
                    l.unit_cost or 0.0,
                    l.opening_value or 0.0,
                    l.movement_value or 0.0,
                    l.balance_value or 0.0,
                ]
            )

        # autosize
        for col in range(1, len(headers) + 1):
            max_len = 0
            for cell in ws[get_column_letter(col)]:
                try:
                    max_len = max(max_len, len(str(cell.value or "")))
                except Exception:
                    pass
            ws.column_dimensions[get_column_letter(col)].width = min(max_len + 2, 45)

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        fname = "stock_period_report_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self.xlsx_filename = fname
        self.xlsx_file = base64.b64encode(bio.read())

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%s&field=xlsx_file&filename_field=xlsx_filename&download=true"
            % (self._name, self.id),
            "target": "self",
        }


class StockPeriodReportLine(models.TransientModel):
    _name = "stock.period.report.line"
    _description = "Stock Period Report Line"
    _order = "product_id, date, id"

    wizard_id = fields.Many2one("stock.period.report.wizard", required=True, ondelete="cascade")

    is_opening = fields.Boolean(default=False)
    is_closing = fields.Boolean(default=False)

    date = fields.Datetime()
    product_id = fields.Many2one("product.product", required=True, index=True)

    picking_id = fields.Many2one("stock.picking")
    move_id = fields.Many2one("stock.move")

    reference = fields.Char()
    movement_type = fields.Selection(
        [
            ("OPEN", "افتتاحي"),
            ("IN", "وارد"),
            ("OUT", "صادر"),
            ("INT", "تحويل داخلي"),
            ("CLOSE", "ختامي"),
            ("SUM", "ملخص"),
            ("SUMLOC", "ملخص (حسب الموقع)"),
        ],
        default="IN",
        index=True,
    )

    location_id = fields.Many2one("stock.location", string="From/Location")
    location_dest_id = fields.Many2one("stock.location", string="To")

    qty_opening = fields.Float(string="Opening Qty")
    qty_in = fields.Float(string="Qty In")
    qty_out = fields.Float(string="Qty Out")
    balance_qty = fields.Float(string="Balance Qty")

    unit_cost = fields.Float(string="Unit Cost")
    opening_value = fields.Float(string="Opening Value")
    movement_value = fields.Float(string="Movement Value")
    balance_value = fields.Float(string="Balance Value")
