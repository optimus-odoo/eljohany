# -*- coding: utf-8 -*-
import base64
from collections import defaultdict
import io

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class StockItemStatusReportWizard(models.TransientModel):
    _name = "stock.item.status.report.wizard"
    _description = "Stock Item Status Report Wizard"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    location_ids = fields.Many2many(
        "stock.location",
        string="Locations",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        required=True,
    )
    include_child_locations = fields.Boolean(string="Include Child Locations", default=True)

    # Branches (res.branch)
    branch_ids = fields.Many2many(
        "res.branch",
        string="Branches")

    date_from = fields.Date(string="From", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="To", required=True, default=fields.Date.context_today)

    product_categ_ids = fields.Many2many("product.category", string="Product Category")
    product_ids = fields.Many2many(
        "product.product",
        string="Products",
        domain="[('company_id', 'in', [company_id, False])]",
    )
    order_point = fields.Float()

    @api.onchange("company_id")
    def _onchange_company_id(self):
        """Discard products that do not belong to the newly selected company."""
        for wizard in self:
            wizard.product_ids = wizard.product_ids.filtered(
                lambda product: not product.company_id
                or product.company_id == wizard.company_id
            )
    # ----------------------------
    # Public Actions
    # ----------------------------
    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("xlsxwriter python library is required to export Excel."))

        lines = self._prepare_lines()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        ws = workbook.add_worksheet("تقرير المخزون")
        header_fmt = workbook.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter"})
        cell_fmt = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})
        num_fmt = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter", "num_format": "#,##0.00"})
        qty_fmt = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter", "num_format": "#,##0.###"})

        headers = [
            "كود الصنف",
            "فئة المنتج",
            "اسم المنتج",
            "المورد",
            "تكلفة الوحدة",
            "الكمية الحالية",
            "حد الطلب",
            "الكمية المباعة",
            "اجمالي قيمة المخزون",
            "حالة الصنف",
        ]

        col_widths = [14, 24, 32, 24, 14, 14, 12, 14, 18, 12]
        for i, w in enumerate(col_widths):
            ws.set_column(i, i, w)

        ws.freeze_panes(1, 0)
        for c, h in enumerate(headers):
            ws.write(0, c, h, header_fmt)

        row = 1
        for l in lines:
            ws.write(row, 0, l.get("default_code") or "", cell_fmt)
            ws.write(row, 1, l.get("product_categ") or "", cell_fmt)
            ws.write(row, 2, l.get("product_name") or "", cell_fmt)
            ws.write(row, 3, l.get("vendor_name") or "", cell_fmt)
            ws.write_number(row, 4, float(l.get("unit_cost") or 0.0), num_fmt)
            ws.write_number(row, 5, float(l.get("qty_on_hand") or 0.0), qty_fmt)
            ws.write_number(row, 6, float(l.get("reorder_point") or 0.0), qty_fmt)
            ws.write_number(row, 7, float(l.get("qty_sold") or 0.0), qty_fmt)
            ws.write_number(row, 8, float(l.get("stock_value") or 0.0), num_fmt)
            ws.write(row, 9, l.get("status") or "", cell_fmt)
            row += 1

        workbook.close()
        output.seek(0)

        attachment = self.env["ir.attachment"].sudo().create({
            "name": "Stock_Item_Status_Report.xlsx",
            "type": "binary",
            "datas": base64.b64encode(output.getvalue()),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("stock_item_status_report.action_stock_item_status_report_pdf").report_action(
            self, data={"wizard_id": self.id}
        )

    # ----------------------------
    # Helpers
    # ----------------------------
    def _has_field(self, model_name, field_name):
        return field_name in self.env[model_name]._fields

    # ----------------------------
    # Data Prep
    # ----------------------------
    def _prepare_lines(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("From date must be before To date."))

        company = self.company_id
        wiz = self.sudo().with_company(company).with_context(allowed_company_ids=[company.id])

        products = wiz._get_products()
        if not products:
            return []

        qty_map = wiz._get_on_hand_by_product(products)

        reorder_map = wiz._get_reorder_point_by_product(products)
        # sold_map = wiz._get_sold_qty_by_product(products)
        sold_map = wiz._get_sold_net_from_sale_order(products)

        vendor_qty_map = wiz._get_vendor_on_hand_by_product(products, qty_map)

        lines = []
        for p in products.sorted(lambda x: (x.default_code or "", x.display_name or "")):
            product_qty_on_hand = qty_map.get(p.id, 0.0)
            sold = sold_map.get(p.id, 0.0)
            unit_cost = p.standard_price or 0.0

            threshold = self.order_point
            remaining = product_qty_on_hand - sold

            status = "طلب فوري" if remaining < threshold else "امن"
            reorder = 0 if threshold < remaining else abs(remaining)

            status = wiz._compute_status(product_qty_on_hand, reorder)

            for vendor_qty in vendor_qty_map[p.id]:
                qty_on_hand = vendor_qty["quantity"]
                lines.append({
                    "product_id": p.id,
                    "vendor_id": vendor_qty["vendor_id"],
                    "default_code": p.default_code or "",
                    "product_categ": p.categ_id.name or "",
                    "product_name": p.display_name or "",
                    "vendor_name": vendor_qty["vendor_name"],
                    "unit_cost": unit_cost,
                    "qty_on_hand": qty_on_hand,
                    "reorder_point": reorder,
                    "qty_sold": sold,
                    "stock_value": qty_on_hand * unit_cost,
                    "status": status,
                })
        return lines

    def _get_products(self):
        self.ensure_one()
        domain = [
            ("type", "in", ["product", "consu"]),
            ("company_id", "in", [self.company_id.id, False]),
        ]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.product_categ_ids:
            domain.append(("categ_id", "in", self.product_categ_ids.ids))
        return self.env["product.product"].search(domain)

    def _location_domain(self):
        self.ensure_one()
        if self.include_child_locations:
            return [("location_id", "child_of", self.location_ids.ids)]
        return [("location_id", "in", self.location_ids.ids)]

    def _get_on_hand_by_product(self, products):
        self.ensure_one()
        domain = self._location_domain() + [
            ("product_id", "in", products.ids),
            ("company_id", "=", self.company_id.id),
        ]
        # optional branch filter if stock.quant has branch_id
        if self.branch_ids and self._has_field("stock.quant", "branch_id"):
            domain.append(("branch_id", "in", self.branch_ids.ids))

        groups = self.env["stock.quant"].read_group(domain, ["quantity:sum"], ["product_id"])
        return {g["product_id"][0]: g["quantity"] for g in groups if g.get("product_id")}

    def _get_vendor_on_hand_by_product(self, products, qty_map):
        """Split current on-hand quantity by the vendor of the remaining receipts.

        Odoo does not store a vendor directly on ``stock.quant``.  Remaining stock
        valuation layers preserve the receipt quantities still in stock and their
        originating purchase moves, so they are the reliable vendor source here.

        Valuation layers are company-wide while the report may target a subset of
        locations.  The vendor shares are therefore reconciled proportionally to
        the selected ``stock.quant`` total.  Quantities without their own vendor
        trace are absorbed by the known vendor shares instead of creating a
        synthetic vendor row.  When there is no vendor trace at all, the product
        is kept in the report with an empty vendor value.
        """
        self.ensure_one()
        vendor_quantities = defaultdict(lambda: defaultdict(float))
        vendor_names = {}

        domain = [
            ("company_id", "=", self.company_id.id),
            ("product_id", "in", products.ids),
            ("remaining_qty", ">", 0),
            ("stock_move_id", "!=", False),
        ]
        if self.branch_ids and self._has_field("stock.move", "branch_id"):
            domain.append(("stock_move_id.branch_id", "in", self.branch_ids.ids))

        layers = self.env["stock.valuation.layer"].sudo().search(domain)
        for layer in layers:
            move = layer.stock_move_id
            purchase_line = move.purchase_line_id
            vendor = purchase_line.order_id.partner_id if purchase_line else False
            if not vendor and move.location_id.usage == "supplier":
                vendor = move.picking_id.partner_id
            if not vendor:
                continue

            vendor = vendor.commercial_partner_id
            vendor_quantities[layer.product_id.id][vendor.id] += layer.remaining_qty
            vendor_names[vendor.id] = vendor.display_name

        result = {}
        for product in products:
            buckets = [
                {
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_names[vendor_id],
                    "quantity": quantity,
                }
                for vendor_id, quantity in vendor_quantities[product.id].items()
                if float_compare(
                    quantity,
                    0.0,
                    precision_rounding=product.uom_id.rounding,
                ) > 0
            ]
            result[product.id] = self._reconcile_vendor_quantities(
                product,
                buckets,
                qty_map.get(product.id, 0.0),
            )
        return result

    def _reconcile_vendor_quantities(self, product, buckets, qty_on_hand):
        """Make vendor buckets total exactly the report's selected on-hand qty."""
        rounding = product.uom_id.rounding

        if float_compare(qty_on_hand, 0.0, precision_rounding=rounding) <= 0:
            return [{
                "vendor_id": False,
                "vendor_name": "",
                "quantity": qty_on_hand,
            }]

        buckets = [dict(bucket) for bucket in buckets]
        attributed_qty = sum(bucket["quantity"] for bucket in buckets)
        if float_is_zero(attributed_qty, precision_rounding=rounding):
            return [{
                "vendor_id": False,
                "vendor_name": "",
                "quantity": qty_on_hand,
            }]

        if float_compare(
            attributed_qty,
            qty_on_hand,
            precision_rounding=rounding,
        ) != 0:
            ratio = qty_on_hand / attributed_qty
            for bucket in buckets:
                bucket["quantity"] *= ratio

        # Absorb harmless floating-point residue without creating a fake row.
        residue = qty_on_hand - sum(bucket["quantity"] for bucket in buckets)
        if buckets and residue:
            buckets[-1]["quantity"] += residue

        return sorted(
            buckets,
            key=lambda bucket: (
                bucket["vendor_name"] or "",
                bucket["vendor_id"] or 0,
            ),
        )

    def _get_reorder_point_by_product(self, products):
        self.ensure_one()
        loc_dom = [("location_id", "in", self.location_ids.ids)]
        if self.include_child_locations:
            loc_dom = [("location_id", "child_of", self.location_ids.ids)]

        domain = loc_dom + [
            ("product_id", "in", products.ids),
            ("company_id", "=", self.company_id.id),
        ]
        # optional branch filter if orderpoint has branch_id
        if self.branch_ids and self._has_field("stock.warehouse.orderpoint", "branch_id"):
            domain.append(("branch_id", "in", self.branch_ids.ids))

        groups = self.env["stock.warehouse.orderpoint"].read_group(domain, ["product_min_qty:sum"], ["product_id"])
        return {g["product_id"][0]: g["product_min_qty"] for g in groups if g.get("product_id")}

    def _move_date_domain(self):
        self.ensure_one()
        df, dt = self.date_from, self.date_to
        return [
            "|",
            "&", ("move_id.invoice_date", ">=", df), ("move_id.invoice_date", "<=", dt),
            "&", ("move_id.date", ">=", df), ("move_id.date", "<=", dt),
        ]

    def _get_return_qty_from_sale_order(self, products):
        """Return qty from sale orders (negative quantities)."""
        self.ensure_one()
    
        domain = [
            ("product_id", "in", products.ids),
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.date_order", ">=", self.date_from),
            ("order_id.date_order", "<=", self.date_to),
            ("product_uom_qty", "<", 0),
        ]
    
        if self.branch_ids and "branch_id" in self.env["sale.order"]._fields:
            domain.append(("order_id.branch_id", "in", self.branch_ids.ids))
    
        groups = self.env["sale.order.line"].read_group(
            domain,
            ["product_uom_qty:sum"],
            ["product_id"],
        )
    
        # make positive
        return {g["product_id"][0]: abs(g["product_uom_qty"]) for g in groups if g.get("product_id")}
    
    def _get_sold_net_from_sale_order(self, products):
        self.ensure_one()
        sold = self._get_sold_qty_from_sale_order(products)
        returned = self._get_return_qty_from_sale_order(products)
        return {pid: sold.get(pid, 0.0) - returned.get(pid, 0.0) for pid in products.ids}
        
    def _get_sold_qty_from_sale_order(self, products):
        """Sold qty from confirmed sale orders (qty delivered)."""
        self.ensure_one()
    
        domain = [
            ("product_id", "in", products.ids),
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.date_order", ">=", self.date_from),
            ("order_id.date_order", "<=", self.date_to),
        ]
    
        # branch filter (if exists on sale.order)
        if self.branch_ids and "branch_id" in self.env["sale.order"]._fields:
            domain.append(("order_id.branch_id", "in", self.branch_ids.ids))
    
        groups = self.env["sale.order.line"].read_group(
            domain,
            ["qty_delivered:sum"],
            ["product_id"],
        )
        return {g["product_id"][0]: g["qty_delivered"] for g in groups if g.get("product_id")}
        
    def _get_sold_qty_by_product(self, products):
        self.ensure_one()
        if not products:
            return {}
    
        product_ids = set(products.ids)
        sold = {pid: 0.0 for pid in product_ids}
    
        # date fallback: invoice_date OR accounting date
        df, dt = self.date_from, self.date_to
        date_domain = [
            "|",
            "&", ("invoice_date", ">=", df), ("invoice_date", "<=", dt),
            "&", ("date", ">=", df), ("date", "<=", dt),
        ]
    
        # Customer Invoices
        inv_domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
        ] + date_domain
    
        # Credit Notes
        ref_domain = [
            ("move_type", "=", "out_refund"),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
        ] + date_domain
    
        # ✅ Branch filter
        if self.branch_ids and "branch_id" in self.env["account.move"]._fields:
            inv_domain.append(("branch_id", "in", self.branch_ids.ids))
            ref_domain.append(("branch_id", "in", self.branch_ids.ids))
    
        invoices = self.env["account.move"].search(inv_domain, order="invoice_date desc, date desc, id desc")
        refunds = self.env["account.move"].search(ref_domain, order="invoice_date desc, date desc, id desc")
    
        # ✅ OPTIONAL: لو تبغى Sold Qty مربوط بالمواقع (لأن عندك Location في invoice line)
        # فعّل هذا الجزء فقط إذا عندكم فعلاً field اسمه location_id على account.move.line
        
        has_line_location = "location_id" in self.env["account.move.line"]._fields
        def _line_ok(line):
            if not line.product_id or line.display_type:
                return False
            if line.product_id.id not in product_ids:
                return False
            if has_line_location and self.location_ids:
                # إذا تبغى child_of هنا نقدر نغيرها، حالياً in فقط
                if line.location_id.id not in self.location_ids.ids:
                    return False
            return True
    
        for move in invoices:
            for line in move.invoice_line_ids:
                if _line_ok(line):
                    sold[line.product_id.id] += (line.quantity or 0.0)
    
        for move in refunds:
            for line in move.invoice_line_ids:
                if _line_ok(line):
                    sold[line.product_id.id] -= (line.quantity or 0.0)
    
        return sold
    def _get_sold_qty_simple(self, products):
        """Sold qty from posted customer invoices only (out_invoice) + branch filter."""
        self.ensure_one()
    
        domain = [
            ("product_id", "in", products.ids),
            ("display_type", "=", False),
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "=", "out_invoice"),
            ("move_id.company_id", "=", self.company_id.id),
            ("move_id.invoice_date", ">=", self.date_from),
            ("move_id.invoice_date", "<=", self.date_to),
        ]
    
        # ✅ branch filter
        if self.branch_ids:
            domain.append(("move_id.branch_id", "in", self.branch_ids.ids))
    
        groups = self.env["account.move.line"].read_group(
            domain,
            ["quantity:sum"],
            ["product_id"],
        )
        return {g["product_id"][0]: g["quantity"] for g in groups if g.get("product_id")}
    def _compute_status(self, qty_on_hand, reorder_point):
        if qty_on_hand <= 0:
            return "لا يوجد"
        if reorder_point and qty_on_hand <= reorder_point:
            return "طلب فوري"
        if reorder_point and qty_on_hand <= (reorder_point * 1.2):
            return "منخفض"
        return "امن"
