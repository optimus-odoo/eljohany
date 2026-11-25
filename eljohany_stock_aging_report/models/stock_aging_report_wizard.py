# -*- coding: utf-8 -*-
import base64
import io

from odoo import api, fields, models, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class EljohanyStockAgingReportWizard(models.TransientModel):
    _name = "eljohany.stock.aging.report.wizard"
    _description = "Eljohany Stock Aging Report Wizard"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    branch_ids = fields.Many2many("res.branch", string="Branches")
    location_ids = fields.Many2many(
        "stock.location",
        string="Locations",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        required=True,
    )
    include_child_locations = fields.Boolean(string="Include Child Locations", default=True)
    date_from = fields.Date(string="From", compute="_compute_date_from")
    date_to = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    product_categ_ids = fields.Many2many("product.category", string="Product Categories")
    product_ids = fields.Many2many("product.product", string="Products")

    @api.depends("date_to")
    def _compute_date_from(self):
        for wizard in self:
            report_date = fields.Date.to_date(wizard.date_to) or fields.Date.context_today(wizard)
            wizard.date_from = report_date.replace(month=1, day=1)

    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("xlsxwriter python library is required to export Excel."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("تقرير أعمار المخزون")
        worksheet.right_to_left()

        header_format = workbook.add_format({
            "bold": True,
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        cell_format = workbook.add_format({
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        money_format = workbook.add_format({
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0.00",
        })
        qty_format = workbook.add_format({
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0.###",
        })

        headers = [
            "الصنف",
            "التكلفة",
            "الكمية الحالية",
            "إجمالي التكلفة",
            "فئة المنتج",
            "الكمية المباعة خلال الفترة",
            "عمر الصنف في المخزون من ١ إلى ٣٠",
            "من ٣١ إلى ٦٠",
            "من ٦١ إلى ٩٠",
            "من ٩١ إلى ١٢٠",
            "من ١٢١ إلى ١٥٠",
            "من ١٥١ إلى ١٨٠",
            "من ١٨١ إلى ما لا نهاية",
        ]
        headers.insert(6, "Invoiced Qty")
        widths = [36, 14, 14, 18, 24, 18, 14, 24, 18, 18, 18, 18, 18, 24]

        worksheet.write(0, 0, "الفترة", header_format)
        worksheet.write(0, 1, f"{self.date_from} - {self.date_to}", cell_format)
        worksheet.freeze_panes(3, 0)
        for column, width in enumerate(widths):
            worksheet.set_column(column, column, width)
        for column, header in enumerate(headers):
            worksheet.write(2, column, header, header_format)

        for row, line in enumerate(self._prepare_lines(), start=3):
            worksheet.write(row, 0, line["product_name"], cell_format)
            worksheet.write_number(row, 1, line["unit_cost"], money_format)
            worksheet.write_number(row, 2, line["qty_on_hand"], qty_format)
            worksheet.write_number(row, 3, line["total_cost"], money_format)
            worksheet.write(row, 4, line["category_name"], cell_format)
            worksheet.write_number(row, 5, line["sold_qty_period"], qty_format)
            worksheet.write_number(row, 6, line["invoiced_qty_period"], qty_format)
            worksheet.write_number(row, 7, line["age_1_30"], qty_format)
            worksheet.write_number(row, 8, line["age_30_60"], qty_format)
            worksheet.write_number(row, 9, line["age_60_90"], qty_format)
            worksheet.write_number(row, 10, line["age_90_120"], qty_format)
            worksheet.write_number(row, 11, line["age_120_150"], qty_format)
            worksheet.write_number(row, 12, line["age_150_180"], qty_format)
            worksheet.write_number(row, 13, line["age_180_plus"], qty_format)

        workbook.close()
        output.seek(0)

        attachment = self.env["ir.attachment"].sudo().create({
            "name": "Eljohany_Stock_Aging_Report.xlsx",
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
        return self.env.ref("eljohany_stock_aging_report.action_eljohany_stock_aging_report_pdf").report_action(
            self.sudo(), data={"wizard_id": self.id}
        )

    def _prepare_lines(self):
        self.ensure_one()
        # Report exports are intentionally generated with elevated read access.
        # Keep the selected company in the environment so sudo does not widen
        # the report beyond the company and filters chosen on the wizard.
        company_wizard = self.sudo().with_company(self.company_id).with_context(
            allowed_company_ids=[self.company_id.id]
        )
        products = company_wizard._get_products()
        if not products:
            return []

        quantity_by_product = company_wizard._get_on_hand_by_product(products)
        sold_qty_by_product = company_wizard._get_sold_qty_by_product(products)
        invoiced_qty_by_product = company_wizard._get_invoiced_qty_by_product(products)
        age_by_product = company_wizard._get_stock_age_buckets_by_product(products)

        lines = []
        for product in products.sorted(lambda rec: (rec.default_code or "", rec.display_name or "")):
            quantity = quantity_by_product.get(product.id, 0.0)
            unit_cost = product.standard_price or 0.0
            age_buckets = age_by_product.get(product.id, self._empty_age_buckets())
            lines.append({
                "product_id": product.id,
                "product_name": self._get_product_name(product),
                "unit_cost": unit_cost,
                "qty_on_hand": quantity,
                "total_cost": quantity * unit_cost,
                "category_name": product.categ_id.display_name or "",
                "sold_qty_period": sold_qty_by_product.get(product.id, 0.0),
                "invoiced_qty_period": invoiced_qty_by_product.get(product.id, 0.0),
                "age_1_30": age_buckets["age_1_30"],
                "age_30_60": age_buckets["age_30_60"],
                "age_60_90": age_buckets["age_60_90"],
                "age_90_120": age_buckets["age_90_120"],
                "age_120_150": age_buckets["age_120_150"],
                "age_150_180": age_buckets["age_150_180"],
                "age_180_plus": age_buckets["age_180_plus"],
            })
        return lines

    def _get_product_name(self, product):
        name = product.display_name or product.name or product.product_tmpl_id.name or ""
        if product.default_code and product.default_code not in name:
            return "[%s] %s" % (product.default_code, name)
        return name or product.default_code or ""

    def _get_products(self):
        self.ensure_one()
        domain = [("type", "in", ["product", "consu"])]
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

    def _has_field(self, model_name, field_name):
        return field_name in self.env[model_name]._fields

    def _get_on_hand_by_product(self, products):
        self.ensure_one()
        domain = self._location_domain() + [
            ("product_id", "in", products.ids),
            ("company_id", "=", self.company_id.id),
        ]
        if self.branch_ids and self._has_field("stock.quant", "branch_id"):
            domain.append(("branch_id", "in", self.branch_ids.ids))

        groups = self.env["stock.quant"].read_group(domain, ["quantity:sum"], ["product_id"])
        return {group["product_id"][0]: group["quantity"] for group in groups if group.get("product_id")}

    def _get_sold_qty_by_product(self, products):
        self.ensure_one()
        domain = self._location_domain() + [
            ("product_id", "in", products.ids),
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("location_dest_id.usage", "=", "customer"),
        ]
        if self.branch_ids and self._has_field("stock.move.line", "branch_id"):
            domain.append(("branch_id", "in", self.branch_ids.ids))

        groups = self.env["stock.move.line"].read_group(domain, ["quantity:sum"], ["product_id"])
        return {group["product_id"][0]: group["quantity"] for group in groups if group.get("product_id")}

    def _get_invoice_line_location_domain(self):
        self.ensure_one()
        field_name = False
        if self._has_field("account.move.line", "stock_location_id"):
            field_name = "stock_location_id"
        elif self._has_field("account.move.line", "location_id"):
            field_name = "location_id"

        if not field_name:
            return []
        if self.include_child_locations:
            return [(field_name, "child_of", self.location_ids.ids)]
        return [(field_name, "in", self.location_ids.ids)]

    def _get_invoiced_qty_by_product(self, products):
        self.ensure_one()
        result = {product.id: 0.0 for product in products}
        if not products:
            return result

        date_domain = [
            "|",
            "&", ("move_id.invoice_date", ">=", self.date_from), ("move_id.invoice_date", "<=", self.date_to),
            "&", ("move_id.date", ">=", self.date_from), ("move_id.date", "<=", self.date_to),
        ]
        common_domain = [
            ("product_id", "in", products.ids),
            ("display_type", "=", False),
            ("move_id.state", "=", "posted"),
            ("move_id.company_id", "=", self.company_id.id),
        ] + date_domain + self._get_invoice_line_location_domain()

        if self.branch_ids:
            if self._has_field("account.move.line", "branch_id"):
                common_domain.append(("branch_id", "in", self.branch_ids.ids))
            elif self._has_field("account.move", "branch_id"):
                common_domain.append(("move_id.branch_id", "in", self.branch_ids.ids))

        for move_type, sign in (("out_invoice", 1.0), ("out_refund", -1.0)):
            groups = self.env["account.move.line"].read_group(
                common_domain + [("move_id.move_type", "=", move_type)],
                ["quantity:sum"],
                ["product_id"],
            )
            for group in groups:
                if group.get("product_id"):
                    result[group["product_id"][0]] += sign * (group.get("quantity") or 0.0)

        return result

    def _empty_age_buckets(self):
        return {
            "age_1_30": 0.0,
            "age_30_60": 0.0,
            "age_60_90": 0.0,
            "age_90_120": 0.0,
            "age_120_150": 0.0,
            "age_150_180": 0.0,
            "age_180_plus": 0.0,
        }

    def _get_stock_age_buckets_by_product(self, products):
        self.ensure_one()
        result = {product.id: self._empty_age_buckets() for product in products}
        if not products or not self._has_field("stock.quant", "in_date"):
            return result

        report_date = fields.Date.to_date(self.date_to) or fields.Date.context_today(self)
        domain = self._location_domain() + [
            ("product_id", "in", products.ids),
            ("company_id", "=", self.company_id.id),
            ("quantity", ">", 0),
        ]
        if self.branch_ids and self._has_field("stock.quant", "branch_id"):
            domain.append(("branch_id", "in", self.branch_ids.ids))

        for quant in self.env["stock.quant"].search(domain):
            in_date = fields.Datetime.to_datetime(quant.in_date)
            if not in_date:
                continue

            buckets = result.setdefault(quant.product_id.id, self._empty_age_buckets())
            age_days = max((report_date - in_date.date()).days, 0)
            quantity = quant.quantity or 0.0

            if age_days <= 30:
                buckets["age_1_30"] += quantity
            elif age_days <= 60:
                buckets["age_30_60"] += quantity
            elif age_days <= 90:
                buckets["age_60_90"] += quantity
            elif age_days <= 120:
                buckets["age_90_120"] += quantity
            elif age_days <= 150:
                buckets["age_120_150"] += quantity
            elif age_days <= 180:
                buckets["age_150_180"] += quantity
            else:
                buckets["age_180_plus"] += quantity

        return result
