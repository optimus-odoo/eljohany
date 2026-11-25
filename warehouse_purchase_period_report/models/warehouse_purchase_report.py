# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover - checked at export time
    Workbook = None


class WarehousePurchaseReportWizard(models.TransientModel):
    _name = "warehouse.purchase.report.wizard"
    _description = "Warehouse Movement Report Wizard"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "warehouse_purchase_report_warehouse_rel",
        "wizard_id",
        "warehouse_id",
        string="Warehouses",
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    date_from = fields.Date(
        string="Date From",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Date To",
        required=True,
        default=fields.Date.context_today,
    )
    product_ids = fields.Many2many(
        "product.product",
        "warehouse_purchase_report_product_rel",
        "wizard_id",
        "product_id",
        string="Products",
        domain=(
            "[('type', '=', 'product'), '|', ('company_id', '=', False), "
            "('company_id', '=', company_id)]"
        ),
        help="Leave empty to include all storable products.",
    )
    line_ids = fields.One2many(
        "warehouse.purchase.report.line",
        "wizard_id",
        string="Report Lines",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )
    contains_estimated_cost = fields.Boolean(
        string="Contains Estimated Cost",
        compute="_compute_summary",
    )
    total_value = fields.Monetary(
        string="Grand Total",
        compute="_compute_summary",
        currency_field="currency_id",
    )
    xlsx_file = fields.Binary(string="Excel File", readonly=True, attachment=False)
    xlsx_filename = fields.Char(string="Excel Filename", readonly=True)

    @api.depends("line_ids.estimated_cost", "line_ids.total_value")
    def _compute_summary(self):
        for wizard in self:
            wizard.contains_estimated_cost = any(
                wizard.line_ids.mapped("estimated_cost")
            )
            wizard.total_value = wizard.currency_id.round(
                sum(wizard.line_ids.mapped("total_value"))
            )

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("Date From must be before or equal to Date To."))

    @api.constrains("company_id", "warehouse_ids")
    def _check_warehouse_companies(self):
        for wizard in self:
            invalid = wizard.warehouse_ids.filtered(
                lambda warehouse: warehouse.company_id != wizard.company_id
            )
            if invalid:
                raise ValidationError(
                    _("All selected warehouses must belong to the selected company.")
                )

    @api.constrains("company_id", "product_ids")
    def _check_product_companies(self):
        for wizard in self:
            invalid = wizard.product_ids.filtered(
                lambda product: product.company_id
                and product.company_id != wizard.company_id
            )
            if invalid:
                raise ValidationError(
                    _("All selected products must belong to the selected company or be shared.")
                )

    def _validate_options(self):
        self.ensure_one()
        self._check_date_range()
        self._check_warehouse_companies()
        self._check_product_companies()
        if self.company_id not in self.env.user.company_ids:
            raise AccessError(_("You are not allowed to report on the selected company."))
        if not self.warehouse_ids:
            raise UserError(_("Select at least one warehouse."))

    def _utc_period_bounds(self):
        """Return a half-open UTC period matching the user's local calendar dates."""
        self.ensure_one()
        user_timezone = pytz.timezone(
            self.env.context.get("tz") or self.env.user.tz or "UTC"
        )
        start_local = user_timezone.localize(
            datetime.combine(fields.Date.to_date(self.date_from), time.min)
        )
        end_local = user_timezone.localize(
            datetime.combine(fields.Date.to_date(self.date_to) + timedelta(days=1), time.min)
        )
        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return fields.Datetime.to_string(start_utc), fields.Datetime.to_string(end_utc)

    def _warehouse_location_map(self):
        """Map each internal child location to exactly one selected warehouse."""
        self.ensure_one()
        location_to_warehouse = {}
        for warehouse in self.warehouse_ids.sorted("id"):
            locations = self.env["stock.location"].search(
                [
                    ("id", "child_of", warehouse.view_location_id.id),
                    ("usage", "=", "internal"),
                    ("company_id", "in", (False, self.company_id.id)),
                ]
            )
            for location in locations:
                location_to_warehouse.setdefault(location.id, warehouse.id)
        return location_to_warehouse

    def _get_period_move_lines(self, internal_location_ids):
        """Return completed supplier/customer movements crossing a warehouse."""
        self.ensure_one()
        date_start, date_end = self._utc_period_bounds()
        external_usages = ("supplier", "customer")
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("date", ">=", date_start),
            ("date", "<", date_end),
            ("product_id.type", "=", "product"),
            "|",
            "&",
            ("location_id", "in", internal_location_ids),
            ("location_dest_id.usage", "in", external_usages),
            "&",
            ("location_dest_id", "in", internal_location_ids),
            ("location_id.usage", "in", external_usages),
        ]
        if self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))
        return self.env["stock.move.line"].search(domain, order="date, id")

    def _get_opening_move_lines(self, internal_location_ids):
        """Return completed movements used to reconstruct opening quantities."""
        self.ensure_one()
        date_start, _date_end = self._utc_period_bounds()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("date", "<", date_start),
            ("product_id.type", "=", "product"),
            "|",
            ("location_id", "in", internal_location_ids),
            ("location_dest_id", "in", internal_location_ids),
        ]
        if self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))
        return self.env["stock.move.line"].search(domain, order="date, id")

    @staticmethod
    def _quantity_in_product_uom(move_line):
        return move_line.quantity_product_uom

    @staticmethod
    def _purchase_line_for_move(move):
        """Find the purchase line on a receipt or on its return-chain origin."""
        move = move.sudo()
        checked_move_ids = set()
        while move and move.id not in checked_move_ids:
            checked_move_ids.add(move.id)
            if move.purchase_line_id:
                return move.purchase_line_id
            move = move.origin_returned_move_id
        return False

    def _cost_by_move(self, move_lines):
        """Return absolute inventory movement cost and estimation status by move."""
        self.ensure_one()
        moves = move_lines.mapped("move_id")
        move_ids = moves.ids
        if not move_ids:
            return {}, {}

        quantity_by_move = defaultdict(float)
        date_by_move = {}
        for move_line in move_lines:
            move_id = move_line.move_id.id
            quantity_by_move[move_id] += self._quantity_in_product_uom(move_line)
            date_by_move[move_id] = max(
                date_by_move.get(move_id, move_line.date),
                move_line.date,
            )

        layers = self.env["stock.valuation.layer"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("stock_move_id", "in", move_ids),
            ]
        )
        valuation_by_move = defaultdict(float)
        valuation_quantity_by_move = defaultdict(float)
        moves_with_layers = set()
        for layer in layers:
            move_id = layer.stock_move_id.id
            moves_with_layers.add(move_id)
            valuation_by_move[move_id] += layer.value
            valuation_quantity_by_move[move_id] += layer.quantity

        cost_by_move = {}
        source_by_move = {}
        for move in moves:
            purchase_line = self._purchase_line_for_move(move)
            quantity = quantity_by_move[move.id]
            valuation_quantity = valuation_quantity_by_move[move.id]
            if move.id in moves_with_layers and valuation_quantity:
                unit_cost = abs(valuation_by_move[move.id] / valuation_quantity)
                cost_by_move[move.id] = quantity * unit_cost
                source_by_move[move.id] = "inventory_valuation"
            elif purchase_line and purchase_line.product_qty:
                purchase_unit_price = (
                    purchase_line.price_subtotal / purchase_line.product_qty
                )
                product_unit_price = purchase_line.product_uom._compute_price(
                    purchase_unit_price,
                    move.product_id.uom_id,
                )
                order_currency = purchase_line.order_id.currency_id
                movement_date = fields.Datetime.context_timestamp(
                    self,
                    date_by_move[move.id],
                ).date()
                cost_by_move[move.id] = abs(
                    order_currency._convert(
                        quantity * product_unit_price,
                        self.company_id.currency_id,
                        self.company_id,
                        movement_date,
                    )
                )
                source_by_move[move.id] = "purchase_order"
            else:
                cost_by_move[move.id] = abs(
                    quantity * move.product_id.standard_price
                )
                source_by_move[move.id] = "estimated"
        return cost_by_move, source_by_move

    def _opening_cost_by_product(self, products):
        """Return company average cost immediately before the period."""
        self.ensure_one()
        if not products:
            return {}, {}

        date_start, _date_end = self._utc_period_bounds()
        layers = self.env["stock.valuation.layer"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "in", products.ids),
                "|",
                "&",
                ("stock_move_id", "!=", False),
                ("stock_move_id.date", "<", date_start),
                "&",
                ("stock_move_id", "=", False),
                ("create_date", "<", date_start),
            ]
        )
        quantity_by_product = defaultdict(float)
        value_by_product = defaultdict(float)
        for layer in layers:
            product_id = layer.product_id.id
            quantity_by_product[product_id] += layer.quantity
            value_by_product[product_id] += layer.value

        cost_by_product = {}
        source_by_product = {}
        for product in products:
            valuation_quantity = quantity_by_product[product.id]
            if valuation_quantity:
                cost_by_product[product.id] = (
                    value_by_product[product.id] / valuation_quantity
                )
                source_by_product[product.id] = "inventory_valuation"
            else:
                cost_by_product[product.id] = (
                    product.with_company(self.company_id).sudo().standard_price
                )
                source_by_product[product.id] = "estimated"
        return cost_by_product, source_by_product

    def _prepare_lines(self):
        self.ensure_one()
        self._validate_options()
        location_to_warehouse = self._warehouse_location_map()
        if not location_to_warehouse:
            raise UserError(_("No internal locations were found for the selected warehouses."))

        internal_location_ids = list(location_to_warehouse)
        opening_move_lines = self._get_opening_move_lines(internal_location_ids)
        move_lines = self._get_period_move_lines(internal_location_ids)
        products = opening_move_lines.mapped("product_id") | move_lines.mapped(
            "product_id"
        )
        opening_cost_by_product, opening_source_by_product = (
            self._opening_cost_by_product(products)
        )
        cost_by_move, source_by_move = self._cost_by_move(move_lines)
        quantity_by_move = defaultdict(float)
        for move_line in move_lines:
            quantity_by_move[move_line.move_id.id] += self._quantity_in_product_uom(
                move_line
            )

        grouped = defaultdict(
            lambda: {
                "opening_quantity": 0.0,
                "opening_value": 0.0,
                "period_net_quantity": 0.0,
                "net_purchase_quantity": 0.0,
                "net_purchase_value": 0.0,
                "cost_sources": set(),
            }
        )
        for move_line in opening_move_lines:
            quantity = self._quantity_in_product_uom(move_line)
            product = move_line.product_id
            key_suffix = product.uom_id.id
            source_warehouse_id = location_to_warehouse.get(
                move_line.location_id.id
            )
            destination_warehouse_id = location_to_warehouse.get(
                move_line.location_dest_id.id
            )
            for warehouse_id, signed_quantity in (
                (source_warehouse_id, -quantity),
                (destination_warehouse_id, quantity),
            ):
                if not warehouse_id or not signed_quantity:
                    continue
                bucket = grouped[(warehouse_id, key_suffix)]
                bucket["opening_quantity"] += signed_quantity
                bucket["opening_value"] += signed_quantity * (
                    opening_cost_by_product.get(product.id, 0.0)
                )
                bucket["cost_sources"].add(
                    opening_source_by_product.get(product.id, "estimated")
                )

        for move_line in move_lines:
            incoming = move_line.location_dest_id.id in location_to_warehouse
            warehouse_id = location_to_warehouse.get(
                move_line.location_dest_id.id if incoming else move_line.location_id.id
            )
            if not warehouse_id:
                continue
            quantity = self._quantity_in_product_uom(move_line)
            move_quantity = quantity_by_move[move_line.move_id.id]
            allocated_cost = (
                cost_by_move.get(move_line.move_id.id, 0.0) * quantity / move_quantity
                if move_quantity
                else 0.0
            )
            key = (warehouse_id, move_line.product_id.uom_id.id)
            bucket = grouped[key]
            signed_quantity = quantity if incoming else -quantity
            bucket["period_net_quantity"] += signed_quantity
            supplier_movement = (
                move_line.location_id.usage == "supplier"
                or move_line.location_dest_id.usage == "supplier"
            )
            if supplier_movement:
                bucket["net_purchase_quantity"] += signed_quantity
                bucket["net_purchase_value"] += (
                    allocated_cost if incoming else -allocated_cost
                )
                bucket["cost_sources"].add(
                    source_by_move.get(move_line.move_id.id, "estimated")
                )

        currency = self.company_id.currency_id
        result = []
        for warehouse in self.warehouse_ids.sorted(lambda item: item.display_name):
            warehouse_keys = sorted(
                (key for key in grouped if key[0] == warehouse.id),
                key=lambda key: self.env["uom.uom"].browse(key[1]).display_name,
            )
            for key in warehouse_keys:
                values = grouped[key]
                cost_sources = values["cost_sources"]
                if len(cost_sources) == 1:
                    cost_source = next(iter(cost_sources))
                else:
                    cost_source = "mixed"
                average_cost_quantity = (
                    values["opening_quantity"]
                    + values["net_purchase_quantity"]
                )
                average_cost_value = (
                    values["opening_value"] + values["net_purchase_value"]
                )
                closing_quantity = (
                    values["opening_quantity"]
                    + values["period_net_quantity"]
                )
                average_cost = currency.round(
                    average_cost_value / average_cost_quantity
                    if average_cost_quantity
                    else 0.0
                )
                result.append(
                    {
                        "warehouse_id": warehouse.id,
                        "uom_id": key[1],
                        "period_quantity": closing_quantity,
                        "average_cost": average_cost,
                        "total_value": currency.round(
                            closing_quantity * average_cost
                        ),
                        "estimated_cost": "estimated" in cost_sources,
                        "cost_source": cost_source,
                    }
                )
        return result

    def _regenerate_lines(self):
        self.ensure_one()
        values_list = self._prepare_lines()
        self.line_ids.unlink()
        if values_list:
            self.env["warehouse.purchase.report.line"].create(
                [dict(values, wizard_id=self.id) for values in values_list]
            )
        self.xlsx_file = False
        self.xlsx_filename = False

    def action_generate(self):
        self.ensure_one()
        self._regenerate_lines()
        action = self.env.ref(
            "warehouse_purchase_period_report.action_warehouse_purchase_report_lines"
        ).read()[0]
        action["name"] = _("Warehouse Movement: %(date_from)s - %(date_to)s") % {
            "date_from": self.date_from,
            "date_to": self.date_to,
        }
        action["domain"] = [("wizard_id", "=", self.id)]
        action["context"] = {"create": False, "edit": False, "delete": False}
        return action

    def action_print_pdf(self):
        self.ensure_one()
        self._regenerate_lines()
        return self.env.ref(
            "warehouse_purchase_period_report.action_warehouse_purchase_report_pdf"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        if Workbook is None:
            raise UserError(_("openpyxl is not available on the server."))
        self._regenerate_lines()

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = _("Warehouse Movement")[:31]
        worksheet.sheet_view.rightToLeft = (self.env.lang or "").startswith("ar")

        title = _("Warehouse Movement by Period")
        headers = [
            _("Warehouse"),
            _("Unit of Measure"),
            _("Quantity"),
            _("Average Cost"),
            _("Total Value"),
        ]
        worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        worksheet.cell(row=1, column=1, value=title)
        worksheet.cell(row=2, column=1, value=_("Period"))
        worksheet.cell(
            row=2,
            column=2,
            value="%s - %s" % (self.date_from, self.date_to),
        )
        worksheet.append(headers)

        title_fill = PatternFill("solid", fgColor="1F4E78")
        header_fill = PatternFill("solid", fgColor="D9EAF7")
        worksheet.cell(row=1, column=1).fill = title_fill
        worksheet.cell(row=1, column=1).font = Font(color="FFFFFF", bold=True, size=14)
        worksheet.cell(row=1, column=1).alignment = Alignment(horizontal="center")
        for cell in worksheet[3]:
            cell.fill = header_fill
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")

        for line in self.line_ids.sorted(
            lambda item: (item.warehouse_id.display_name, item.uom_id.display_name)
        ):
            worksheet.append(
                [
                    line.warehouse_id.display_name,
                    line.uom_id.display_name,
                    line.period_quantity,
                    line.average_cost,
                    line.total_value,
                ]
            )

        total_row = worksheet.max_row + 1
        worksheet.cell(row=total_row, column=1, value=_("Grand Total"))
        worksheet.cell(row=total_row, column=5, value=self.total_value)
        for cell in worksheet[total_row]:
            cell.font = Font(bold=True)

        for column in range(1, len(headers) + 1):
            max_length = max(
                len(str(worksheet.cell(row=row, column=column).value or ""))
                for row in range(1, worksheet.max_row + 1)
            )
            worksheet.column_dimensions[get_column_letter(column)].width = min(
                max(max_length + 2, 12), 38
            )
        worksheet.freeze_panes = "A4"

        stream = io.BytesIO()
        workbook.save(stream)
        filename = "warehouse_movement_%s_%s.xlsx" % (
            self.date_from,
            self.date_to,
        )
        self.write(
            {
                "xlsx_file": base64.b64encode(stream.getvalue()),
                "xlsx_filename": filename,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=%s&id=%s&field=xlsx_file&"
                "filename_field=xlsx_filename&download=true"
            )
            % (self._name, self.id),
            "target": "self",
        }


class WarehousePurchaseReportLine(models.TransientModel):
    _name = "warehouse.purchase.report.line"
    _description = "Warehouse Movement Report Line"
    _order = "warehouse_id, uom_id, id"

    wizard_id = fields.Many2one(
        "warehouse.purchase.report.wizard",
        required=True,
        ondelete="cascade",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
        readonly=True,
    )
    period_quantity = fields.Float(string="Quantity", readonly=True)
    average_cost = fields.Monetary(
        string="Average Cost",
        currency_field="currency_id",
        readonly=True,
    )
    total_value = fields.Monetary(
        string="Total Value",
        currency_field="currency_id",
        readonly=True,
    )
    estimated_cost = fields.Boolean(string="Estimated Cost", readonly=True)
    cost_source = fields.Selection(
        [
            ("purchase_order", "Purchase Order"),
            ("inventory_valuation", "Inventory Valuation"),
            ("estimated", "Estimated"),
            ("mixed", "Mixed Sources"),
        ],
        string="Cost Status",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="wizard_id.currency_id",
        readonly=True,
    )
