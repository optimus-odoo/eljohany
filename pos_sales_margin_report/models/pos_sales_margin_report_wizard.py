import base64
import io
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - handled with a clear user error
    xlsxwriter = None


class PosSalesMarginReportWizard(models.TransientModel):
    _name = "pos.sales.margin.report.wizard"
    _description = "POS Sales and Margin Report Wizard"

    def _default_date_from(self):
        """Start at midnight on the first day of the current local month."""
        today = fields.Date.context_today(self)
        timezone = pytz.timezone(
            self.env.context.get("tz") or self.env.user.tz or "UTC"
        )
        start_local = timezone.localize(datetime.combine(today.replace(day=1), time.min))
        return start_local.astimezone(pytz.UTC).replace(tzinfo=None)

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    pos_config_ids = fields.Many2many(
        "pos.config",
        string="Points of Sale",
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    date_from = fields.Datetime(
        string="Date and Time From",
        required=True,
        default=_default_date_from,
    )
    date_to = fields.Datetime(
        string="Date and Time To",
        required=True,
        default=fields.Datetime.now,
    )

    def _get_arabic_report_labels(self):
        """Return the fixed Arabic labels used by both exported formats.

        The business requested Arabic Excel and PDF files regardless of the
        interface language of the user exporting the report.
        """
        return {
            "worksheet": "هامش نقطة البيع",
            "title": "تقرير مبيعات وهوامش نقاط البيع",
            "company": "الشركة",
            "currency": "العملة",
            "points_of_sale": "نقاط البيع",
            "period": "الفترة",
            "to": "إلى",
            "warning": (
                "تنبيه: يوجد %(count)s سطر طلب لم تُحتسب تكلفته بعد. "
                "قد تتغير قيم هامش الربح بعد إغلاق جلسات نقاط البيع المرتبطة."
            ),
            "headers": [
                "اسم المنتج",
                "الكمية",
                "المجموع",
                "الخصومات",
                "المجموع بعد الخصومات",
                "الضريبة",
                "المجموع العام",
                "هامش الربح - مبلغ",
                "هامش الربح - نسبة",
            ],
            "total": "الإجمالي",
            "no_data": "لا توجد بيانات وفق عوامل التصفية المختارة.",
        }

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wizard in self:
            wizard.pos_config_ids = wizard.pos_config_ids.filtered(
                lambda config: config.company_id == wizard.company_id
            )

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _(
                        "Date and Time From must be before or equal to "
                        "Date and Time To."
                    )
                )

    @api.constrains("company_id", "pos_config_ids")
    def _check_pos_companies(self):
        for wizard in self:
            invalid_configs = wizard.pos_config_ids.filtered(
                lambda config: config.company_id != wizard.company_id
            )
            if invalid_configs:
                raise ValidationError(
                    _("All selected Points of Sale must belong to the selected company.")
                )

    def _validate_report_options(self):
        self.ensure_one()
        self._check_date_range()
        self._check_pos_companies()
        if self.company_id not in self.env.user.company_ids:
            raise AccessError(_("You are not allowed to report on the selected company."))
        if not self.pos_config_ids:
            raise UserError(_("Select at least one Point of Sale."))

    def _get_utc_datetime_bounds(self):
        """Return the exact inclusive UTC timestamps stored by Odoo."""
        self.ensure_one()
        return (
            fields.Datetime.to_string(self.date_from),
            fields.Datetime.to_string(self.date_to),
        )

    def _format_report_datetime(self, value):
        """Display an Odoo UTC datetime in the exporting user's local timezone."""
        self.ensure_one()
        if not value:
            return ""
        local_value = fields.Datetime.context_timestamp(self, value)
        return local_value.strftime("%Y-%m-%d %H:%M:%S")

    def _get_report_domain(self):
        self.ensure_one()
        start_utc, end_utc = self._get_utc_datetime_bounds()
        return [
            ("company_id", "=", self.company_id.id),
            ("config_id", "in", self.pos_config_ids.ids),
            ("state", "in", ["paid", "done", "invoiced"]),
            ("date", ">=", start_utc),
            ("date", "<=", end_utc),
        ]

    def _get_order_line_domain(self):
        self.ensure_one()
        start_utc, end_utc = self._get_utc_datetime_bounds()
        return [
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.config_id", "in", self.pos_config_ids.ids),
            ("order_id.state", "in", ["paid", "done", "invoiced"]),
            ("order_id.date_order", ">=", start_utc),
            ("order_id.date_order", "<=", end_utc),
        ]

    def _build_lines_from_groups(
        self, groups, quantity_by_product=None, margin_by_product=None
    ):
        """Translate Odoo's POS analysis measures into the requested columns."""
        self.ensure_one()
        quantity_by_product = quantity_by_product or {}
        currency = self.company_id.currency_id
        lines = []
        for group in groups:
            product_value = group.get("product_id")
            if not product_value:
                continue
            gross_total = group.get("price_sub_total") or 0.0
            discounts = group.get("total_discount") or 0.0
            net_total = gross_total - discounts
            grand_total = group.get("price_total") or 0.0
            tax = grand_total - net_total
            margin = (
                margin_by_product.get(product_value[0], 0.0)
                if margin_by_product is not None
                else group.get("margin") or 0.0
            )
            margin_percent = (
                (margin / net_total) * 100.0
                if not currency.is_zero(net_total)
                else 0.0
            )
            lines.append(
                {
                    "product_id": product_value[0],
                    "product_name": product_value[1],
                    "quantity": quantity_by_product.get(
                        product_value[0], group.get("product_qty") or 0.0
                    ),
                    "gross_total": gross_total,
                    "discounts": discounts,
                    "net_total": net_total,
                    "tax": tax,
                    "grand_total": grand_total,
                    "margin": margin,
                    "margin_percent": margin_percent,
                }
            )
        return sorted(lines, key=lambda line: (line["product_name"] or "").casefold())

    def _get_quantity_and_margin_by_product(self, order_line_model):
        """Aggregate precise quantities and convert margins to company currency."""
        self.ensure_one()
        groups = order_line_model.read_group(
            self._get_order_line_domain(),
            [
                "product_id",
                "order_id",
                "qty:sum",
                "price_subtotal:sum",
                "total_cost:sum",
            ],
            ["product_id", "order_id"],
            lazy=False,
        )
        order_ids = [
            group["order_id"][0] for group in groups if group.get("order_id")
        ]
        rate_by_order = {
            order.id: order.currency_rate or 1.0
            for order in self.env["pos.order"].browse(order_ids)
        }
        return self._aggregate_quantity_and_margin_groups(groups, rate_by_order)

    def _aggregate_quantity_and_margin_groups(self, groups, rate_by_order):
        self.ensure_one()
        quantity_by_product = {}
        margin_by_product = {}
        for group in groups:
            product_value = group.get("product_id")
            order_value = group.get("order_id")
            if not product_value or not order_value:
                continue
            product_id = product_value[0]
            conversion_rate = rate_by_order.get(order_value[0]) or 1.0
            quantity_by_product[product_id] = quantity_by_product.get(
                product_id, 0.0
            ) + (group.get("qty") or 0.0)
            margin_by_product[product_id] = margin_by_product.get(
                product_id, 0.0
            ) + (
                (group.get("price_subtotal") or 0.0)
                - (group.get("total_cost") or 0.0)
            ) / conversion_rate
        return quantity_by_product, margin_by_product

    def _get_totals(self, lines):
        self.ensure_one()
        totals = {
            key: sum(line[key] for line in lines)
            for key in (
                "quantity",
                "gross_total",
                "discounts",
                "net_total",
                "tax",
                "grand_total",
                "margin",
            )
        }
        totals["margin_percent"] = (
            (totals["margin"] / totals["net_total"]) * 100.0
            if not self.company_id.currency_id.is_zero(totals["net_total"])
            else 0.0
        )
        return totals

    def _prepare_report_data(self):
        self.ensure_one()
        self._validate_report_options()
        report_model = self.env["report.pos.order"].with_company(self.company_id)
        groups = report_model.read_group(
            self._get_report_domain(),
            [
                "product_id",
                "product_qty:sum",
                "price_sub_total:sum",
                "total_discount:sum",
                "price_total:sum",
            ],
            ["product_id"],
            lazy=False,
        )
        order_line_model = self.env["pos.order.line"].with_company(self.company_id)
        quantity_by_product, margin_by_product = (
            self._get_quantity_and_margin_by_product(order_line_model)
        )
        lines = self._build_lines_from_groups(
            groups, quantity_by_product, margin_by_product
        )
        uncomputed_cost_count = order_line_model.search_count(
            self._get_order_line_domain() + [("is_total_cost_computed", "=", False)]
        )
        return {
            "lines": lines,
            "totals": self._get_totals(lines),
            "uncomputed_cost_count": uncomputed_cost_count,
        }

    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("The xlsxwriter Python library is required to export Excel."))

        data = self._prepare_report_data()
        labels = self._get_arabic_report_labels()
        date_from_display = self._format_report_datetime(self.date_from)
        date_to_display = self._format_report_datetime(self.date_to)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        worksheet = workbook.add_worksheet(labels["worksheet"][:31])
        worksheet.right_to_left()

        title_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 16,
                "align": "center",
                "valign": "vcenter",
                "bg_color": "#1F4E78",
                "font_color": "#FFFFFF",
            }
        )
        meta_format = workbook.add_format(
            {
                "bold": True,
                "align": "right",
                "valign": "vcenter",
            }
        )
        warning_format = workbook.add_format(
            {
                "bold": True,
                "font_color": "#9C5700",
                "bg_color": "#FFEB9C",
                "text_wrap": True,
            }
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "bg_color": "#D9EAF7",
                "text_wrap": True,
            }
        )
        text_format = workbook.add_format(
            {
                "border": 1,
                "align": "right",
                "valign": "vcenter",
            }
        )
        number_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "#,##0.00;[Red]-#,##0.00",
            }
        )
        quantity_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "#,##0.###;[Red]-#,##0.###",
            }
        )
        percent_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "num_format": "0.00%;[Red]-0.00%",
            }
        )
        total_label_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "bg_color": "#E2F0D9",
            }
        )
        total_number_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "bg_color": "#E2F0D9",
                "num_format": "#,##0.00;[Red]-#,##0.00",
            }
        )
        total_quantity_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "bg_color": "#E2F0D9",
                "num_format": "#,##0.###;[Red]-#,##0.###",
            }
        )
        total_percent_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "bg_color": "#E2F0D9",
                "num_format": "0.00%;[Red]-0.00%",
            }
        )

        worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
        worksheet.set_margins(0.25, 0.25, 0.5, 0.5)
        worksheet.set_column(0, 0, 34)
        worksheet.set_column(1, 1, 13)
        worksheet.set_column(2, 8, 18)
        worksheet.merge_range(0, 0, 0, 8, labels["title"], title_format)
        worksheet.merge_range(
            1,
            0,
            1,
            8,
            "%s: %s | %s: %s"
            % (
                labels["company"],
                self.company_id.display_name,
                labels["currency"],
                self.company_id.currency_id.display_name,
            ),
            meta_format,
        )
        worksheet.merge_range(
            2,
            0,
            2,
            8,
            "%s: %s"
            % (
                labels["points_of_sale"],
                "، ".join(self.pos_config_ids.mapped("display_name")),
            ),
            meta_format,
        )
        worksheet.merge_range(
            3,
            0,
            3,
            8,
            "%s: %s %s %s"
            % (labels["period"], date_from_display, labels["to"], date_to_display),
            meta_format,
        )
        row = 4
        if data["uncomputed_cost_count"]:
            worksheet.merge_range(
                row,
                0,
                row,
                8,
                labels["warning"] % {"count": data["uncomputed_cost_count"]},
                warning_format,
            )
            row += 1

        header_row = row
        for column, header in enumerate(labels["headers"]):
            worksheet.write(header_row, column, header, header_format)
        row += 1

        for line in data["lines"]:
            worksheet.write(row, 0, line["product_name"], text_format)
            worksheet.write_number(row, 1, line["quantity"], quantity_format)
            worksheet.write_number(row, 2, line["gross_total"], number_format)
            worksheet.write_number(row, 3, line["discounts"], number_format)
            worksheet.write_number(row, 4, line["net_total"], number_format)
            worksheet.write_number(row, 5, line["tax"], number_format)
            worksheet.write_number(row, 6, line["grand_total"], number_format)
            worksheet.write_number(row, 7, line["margin"], number_format)
            worksheet.write_number(row, 8, line["margin_percent"] / 100.0, percent_format)
            row += 1

        totals = data["totals"]
        worksheet.write(row, 0, labels["total"], total_label_format)
        worksheet.write_number(row, 1, totals["quantity"], total_quantity_format)
        for column, key in enumerate(
            ("gross_total", "discounts", "net_total", "tax", "grand_total", "margin"),
            start=2,
        ):
            worksheet.write_number(row, column, totals[key], total_number_format)
        worksheet.write_number(
            row,
            8,
            totals["margin_percent"] / 100.0,
            total_percent_format,
        )
        worksheet.autofilter(header_row, 0, max(row - 1, header_row), 8)
        worksheet.freeze_panes(header_row + 1, 1)
        worksheet.repeat_rows(header_row)

        workbook.close()
        output.seek(0)
        filename = "POS_Sales_Margin_%s_%s.xlsx" % (
            fields.Datetime.context_timestamp(self, self.date_from).strftime(
                "%Y%m%d_%H%M%S"
            ),
            fields.Datetime.context_timestamp(self, self.date_to).strftime(
                "%Y%m%d_%H%M%S"
            ),
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(output.getvalue()),
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._validate_report_options()
        return self.env.ref(
            "pos_sales_margin_report.action_pos_sales_margin_report_pdf"
        ).report_action(self, data={"wizard_id": self.id})
