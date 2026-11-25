# -*- coding: utf-8 -*-

import base64
from datetime import datetime, time
import io

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - depends on the Odoo host image
    xlsxwriter = None


class EljohanySlowMovingReportWizard(models.TransientModel):
    _name = "eljohany.slow.moving.report.wizard"
    _description = "Slow Moving Products Report Wizard"

    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self.env.company,
    )
    branch_ids = fields.Many2many(
        "res.branch",
        string="الفروع",
    )
    location_ids = fields.Many2many(
        "stock.location",
        string="مواقع المخزون",
        required=True,
        default=lambda self: self._default_location_ids(),
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    include_child_locations = fields.Boolean(
        string="تضمين المواقع الفرعية",
        default=True,
    )
    report_date = fields.Date(
        string="تاريخ التقرير",
        required=True,
        default=fields.Date.context_today,
    )
    sales_date_from = fields.Date(
        string="مبيعات الفترة من",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(
            month=1, day=1
        ),
        help="بداية الفترة المستخدمة لاحتساب تسليمات العملاء ومرتجعاتهم.",
    )
    sales_date_to = fields.Date(
        string="مبيعات الفترة إلى",
        required=True,
        default=fields.Date.context_today,
        help="نهاية الفترة المستخدمة لاحتساب تسليمات العملاء ومرتجعاتهم.",
    )
    inactivity_days = fields.Integer(
        string="مدة الركود بالأيام",
        required=True,
        default=90,
        help="يظهر المنتج عندما يبلغ رصيده عمر المدة المحددة دون أي تسليم منجز للعميل.",
    )
    product_categ_ids = fields.Many2many(
        "product.category",
        string="فئات المنتجات",
    )
    product_ids = fields.Many2many(
        "product.product",
        string="المنتجات",
        domain="[('company_id', 'in', [company_id, False])]",
    )
    line_ids = fields.One2many(
        "eljohany.slow.moving.report.line",
        "wizard_id",
        string="النتائج",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Keep programmatically created historical reports on valid dates."""
        today = fields.Date.context_today(self)
        prepared_values = []
        for values in vals_list:
            values = dict(values)
            report_date = fields.Date.to_date(
                values.get("report_date") or today
            )
            values.setdefault("sales_date_to", report_date)
            values.setdefault(
                "sales_date_from", report_date.replace(month=1, day=1)
            )
            prepared_values.append(values)
        return super().create(prepared_values)

    def _default_location_ids(self):
        return self._company_warehouse_locations(self.env.company)

    def _warehouse_internal_locations(self, warehouses, company):
        warehouse_views = warehouses.mapped("view_location_id")
        if not warehouse_views:
            return self.env["stock.location"]
        return self.env["stock.location"].search(
            [
                ("id", "child_of", warehouse_views.ids),
                ("usage", "=", "internal"),
                ("company_id", "in", [False, company.id]),
            ]
        )

    def _company_warehouse_locations(self, company):
        """Include Stock/Input/Output locations so multi-step routes stay complete."""
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)]
        )
        return self._warehouse_internal_locations(warehouses, company)

    @api.constrains("inactivity_days")
    def _check_inactivity_days(self):
        for wizard in self:
            if wizard.inactivity_days < 1:
                raise ValidationError(_("يجب أن تكون مدة الركود يومًا واحدًا على الأقل."))

    @api.constrains("sales_date_from", "sales_date_to", "report_date")
    def _check_sales_period(self):
        for wizard in self:
            if wizard.sales_date_from > wizard.sales_date_to:
                raise ValidationError(
                    _("يجب أن تكون بداية فترة المبيعات قبل نهايتها أو مساوية لها.")
                )
            if wizard.sales_date_to > wizard.report_date:
                raise ValidationError(
                    _("لا يمكن أن تتجاوز نهاية فترة المبيعات تاريخ التقرير.")
                )

    @api.onchange("report_date")
    def _onchange_report_date(self):
        for wizard in self:
            if wizard.report_date and (
                not wizard.sales_date_to
                or wizard.sales_date_to > wizard.report_date
            ):
                wizard.sales_date_to = wizard.report_date
            if wizard.report_date and (
                not wizard.sales_date_from
                or wizard.sales_date_from > wizard.sales_date_to
            ):
                wizard.sales_date_from = wizard.report_date.replace(
                    month=1, day=1
                )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wizard in self:
            wizard.location_ids = wizard._company_warehouse_locations(
                wizard.company_id
            )
            wizard.branch_ids = False
            wizard.product_ids = wizard.product_ids.filtered(
                lambda product: not product.company_id
                or product.company_id == wizard.company_id
            )

    @api.onchange("branch_ids")
    def _onchange_branch_ids(self):
        for wizard in self:
            if not wizard.company_id:
                continue
            warehouse_domain = [("company_id", "=", wizard.company_id.id)]
            if wizard.branch_ids:
                warehouse_domain.append(("branch_id", "in", wizard.branch_ids.ids))
            warehouses = self.env["stock.warehouse"].search(warehouse_domain)
            wizard.location_ids = wizard._warehouse_internal_locations(
                warehouses, wizard.company_id
            )

    def _validate_report_options(self):
        self.ensure_one()
        if self.company_id not in self.env.user.company_ids:
            raise UserError(_("لا تملك صلاحية إعداد تقرير للشركة المحددة."))
        if not self.location_ids:
            raise UserError(_("اختر موقع مخزون واحدًا على الأقل."))
        if self.report_date > fields.Date.context_today(self):
            raise UserError(_("لا يمكن إنشاء تقرير الرواكد بتاريخ مستقبلي."))
        invalid_locations = self.location_ids.filtered(
            lambda location: location.usage != "internal"
            or (
                location.company_id
                and location.company_id != self.company_id
            )
        )
        if invalid_locations:
            raise UserError(_("بعض المواقع المختارة لا تتبع الشركة المحددة."))
        if self.branch_ids.filtered(
            lambda branch: branch.company_id != self.company_id
        ):
            raise UserError(_("بعض الفروع المختارة لا تتبع الشركة المحددة."))
        if "branch_ids" in self.env.user._fields:
            unauthorized_branches = self.branch_ids - self.env.user.branch_ids
            if unauthorized_branches:
                raise UserError(_("لا تملك صلاحية الوصول إلى بعض الفروع المختارة."))
        if self.branch_ids and not self._branch_field_name():
            raise UserError(
                _("تعذر تطبيق فلتر الفروع لأن حركة المخزون لا تحتوي على حقل فرع.")
            )

    def _branch_field_name(self):
        if "branch_id" in self.env["stock.move.line"]._fields:
            return "branch_id"
        if "branch_id" in self.env["stock.move"]._fields:
            return "move_id.branch_id"
        return False

    def _with_branch_domain(self, domain):
        field_name = self._branch_field_name()
        if self.branch_ids and field_name:
            return domain + [(field_name, "in", self.branch_ids.ids)]
        return domain

    def _get_location_ids(self):
        self.ensure_one()
        domain = [
            ("usage", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
        ]
        if self.include_child_locations:
            domain.append(("id", "child_of", self.location_ids.ids))
        else:
            domain.append(("id", "in", self.location_ids.ids))
        return self.env["stock.location"].search(domain).ids

    def _get_products(self):
        self.ensure_one()
        domain = [
            ("type", "in", ["product", "consu"]),
            ("company_id", "in", [False, self.company_id.id]),
        ]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.product_categ_ids:
            domain.append(("categ_id", "child_of", self.product_categ_ids.ids))
        return self.env["product.product"].search(domain)

    def _utc_datetime(self, value, end_of_day=False):
        self.ensure_one()
        report_time = time.max if end_of_day else time.min
        timezone = pytz.timezone(self.env.user.tz or "UTC")
        localized = timezone.localize(datetime.combine(value, report_time))
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _report_cutoff(self):
        return self._utc_datetime(fields.Date.to_date(self.report_date), end_of_day=True)

    def _sales_period_bounds(self):
        self.ensure_one()
        return (
            self._utc_datetime(fields.Date.to_date(self.sales_date_from)),
            self._utc_datetime(
                fields.Date.to_date(self.sales_date_to), end_of_day=True
            ),
        )

    def _base_move_line_domain(self, products, cutoff):
        domain = [
            ("product_id", "in", products.ids),
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("date", "<=", cutoff),
        ]
        return self._with_branch_domain(domain)

    def _read_quantity_groups(self, domain):
        """Sum Odoo's stored quantity converted to the product's base UoM."""
        groups = self.env["stock.move.line"].read_group(
            domain,
            ["quantity_product_uom:sum"],
            ["product_id"],
            lazy=False,
        )
        return {
            group["product_id"][0]: group.get("quantity_product_uom", 0.0)
            for group in groups
            if group.get("product_id")
        }

    def _get_quantity_by_product(self, products, location_ids, cutoff):
        """Reconstruct the selected-locations balance at the report cutoff."""
        base_domain = self._base_move_line_domain(products, cutoff)
        incoming = self._read_quantity_groups(
            base_domain
            + [
                ("location_dest_id", "in", location_ids),
                ("location_id", "not in", location_ids),
            ]
        )
        outgoing = self._read_quantity_groups(
            base_domain
            + [
                ("location_id", "in", location_ids),
                ("location_dest_id", "not in", location_ids),
            ]
        )
        return {
            product.id: incoming.get(product.id, 0.0)
            - outgoing.get(product.id, 0.0)
            for product in products
        }

    def _get_period_customer_quantities(
        self, products, location_ids, period_start, cutoff
    ):
        base_domain = self._base_move_line_domain(products, cutoff) + [
            ("date", ">=", period_start)
        ]
        delivered = self._read_quantity_groups(
            base_domain
            + [
                ("location_id", "in", location_ids),
                ("location_dest_id.usage", "=", "customer"),
            ]
        )
        returned = self._read_quantity_groups(
            base_domain
            + [
                ("location_id.usage", "=", "customer"),
                ("location_dest_id", "in", location_ids),
            ]
        )
        return delivered, returned

    def _read_extreme_dates(self, domain, aggregate):
        groups = self.env["stock.move.line"].read_group(
            domain,
            ["date:%s" % aggregate],
            ["product_id"],
            lazy=False,
        )
        result = {}
        for group in groups:
            if not group.get("product_id"):
                continue
            value = group.get("date") or group.get("date_%s" % aggregate)
            if value:
                result[group["product_id"][0]] = fields.Datetime.to_datetime(value)
        return result

    def _get_last_customer_delivery_dates(self, products, location_ids, cutoff):
        domain = self._base_move_line_domain(products, cutoff) + [
            ("location_id", "in", location_ids),
            ("location_dest_id.usage", "=", "customer"),
        ]
        return self._read_extreme_dates(domain, "max")

    def _get_stock_entry_dates(self, products, location_ids, cutoff):
        domain = self._base_move_line_domain(products, cutoff) + [
            ("location_dest_id", "in", location_ids),
            ("location_id", "not in", location_ids),
        ]
        return (
            self._read_extreme_dates(domain, "min"),
            self._read_extreme_dates(domain, "max"),
        )

    def _local_date(self, value):
        if not value:
            return False
        utc_value = fields.Datetime.to_datetime(value)
        return fields.Datetime.context_timestamp(self, utc_value).date()

    def _preferred_vendor_name(self, product):
        sellers = product.seller_ids.filtered(
            lambda seller: (
                not seller.product_id or seller.product_id == product
            )
            and (
                not seller.company_id or seller.company_id == self.company_id
            )
        ).sorted(lambda seller: (seller.sequence, seller.id))
        if not sellers:
            return ""
        return sellers[0].partner_id.commercial_partner_id.display_name or ""

    def _prepare_lines(self):
        self.ensure_one()
        self._validate_report_options()
        report_wizard = self.sudo().with_company(self.company_id).with_context(
            allowed_company_ids=[self.company_id.id]
        )
        products = report_wizard._get_products()
        if not products:
            return []

        location_ids = report_wizard._get_location_ids()
        cutoff = report_wizard._report_cutoff()
        quantity_by_product = report_wizard._get_quantity_by_product(
            products, location_ids, cutoff
        )
        stocked_products = products.filtered(
            lambda product: float_compare(
                quantity_by_product.get(product.id, 0.0),
                0.0,
                precision_rounding=product.uom_id.rounding,
            )
            > 0
        )
        if not stocked_products:
            return []

        last_delivery_by_product = report_wizard._get_last_customer_delivery_dates(
            stocked_products, location_ids, cutoff
        )
        first_entry_by_product, last_entry_by_product = (
            report_wizard._get_stock_entry_dates(
                stocked_products, location_ids, cutoff
            )
        )
        delivered_by_product, returned_by_product = (
            report_wizard._get_period_customer_quantities(
                stocked_products,
                location_ids,
                *report_wizard._sales_period_bounds(),
            )
        )

        report_date = fields.Date.to_date(self.report_date)
        lines = []
        company_products = stocked_products.with_company(self.company_id)
        for product in company_products.sorted(
            lambda record: (record.default_code or "", record.display_name or "")
        ):
            last_delivery_date = report_wizard._local_date(
                last_delivery_by_product.get(product.id)
            )
            first_entry_date = report_wizard._local_date(
                first_entry_by_product.get(product.id)
            )
            last_entry_date = report_wizard._local_date(
                last_entry_by_product.get(product.id)
            )
            if last_delivery_date:
                inactivity_base_date = last_delivery_date
                status = "very_stagnant" if (
                    report_date - inactivity_base_date
                ).days >= self.inactivity_days * 2 else "stagnant"
            else:
                create_date = report_wizard._local_date(product.create_date)
                inactivity_base_date = first_entry_date or create_date or report_date
                status = "never_sold"

            days_inactive = max((report_date - inactivity_base_date).days, 0)
            if days_inactive < self.inactivity_days:
                continue

            quantity = quantity_by_product.get(product.id, 0.0)
            unit_cost = product.standard_price or 0.0
            delivered_qty = delivered_by_product.get(product.id, 0.0)
            returned_qty = returned_by_product.get(product.id, 0.0)
            lines.append(
                {
                    "product_id": product.id,
                    "default_code": product.default_code or "",
                    "product_name": product.display_name or product.name or "",
                    "category_name": product.categ_id.display_name or "",
                    "uom_name": product.uom_id.display_name or "",
                    "vendor_name": report_wizard._preferred_vendor_name(product),
                    "qty_on_hand": quantity,
                    "unit_cost": unit_cost,
                    "stock_value": quantity * unit_cost,
                    "first_stock_date": first_entry_date,
                    "last_receipt_date": last_entry_date,
                    "last_delivery_date": last_delivery_date,
                    "days_inactive": days_inactive,
                    "qty_delivered_period": delivered_qty,
                    "qty_returned_period": returned_qty,
                    "net_qty_sold_period": delivered_qty - returned_qty,
                    "status": status,
                }
            )
        return sorted(
            lines,
            key=lambda line: (
                -line["stock_value"],
                -line["days_inactive"],
                line["default_code"],
                line["product_name"],
            ),
        )

    def _replace_result_lines(self, values_list):
        self.ensure_one()
        self.line_ids.unlink()
        if values_list:
            self.env["eljohany.slow.moving.report.line"].create(
                [dict(values, wizard_id=self.id) for values in values_list]
            )

    def action_view_results(self):
        self.ensure_one()
        self._replace_result_lines(self._prepare_lines())
        action = self.env.ref(
            "eljohany_slow_moving_report.action_slow_moving_report_lines"
        ).read()[0]
        action["domain"] = [("wizard_id", "=", self.id)]
        action["context"] = {
            "create": False,
            "edit": False,
            "delete": False,
        }
        return action

    def action_print_pdf(self):
        self.ensure_one()
        self._replace_result_lines(self._prepare_lines())
        return self.env.ref(
            "eljohany_slow_moving_report.action_slow_moving_products_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("مكتبة xlsxwriter مطلوبة لتصدير ملف Excel."))
        lines = self._prepare_lines()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("المنتجات الراكدة")
        worksheet.right_to_left()
        title_format = workbook.add_format(
            {"bold": True, "font_size": 15, "align": "center"}
        )
        label_format = workbook.add_format(
            {"bold": True, "border": 1, "align": "center", "bg_color": "#D9EAD3"}
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "bg_color": "#1F4E78",
                "font_color": "#FFFFFF",
            }
        )
        cell_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter"}
        )
        qty_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "num_format": "#,##0.###",
            }
        )
        money_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "num_format": "#,##0.00",
            }
        )
        date_format = workbook.add_format(
            {"border": 1, "align": "center", "num_format": "yyyy-mm-dd"}
        )

        headers = [
            "كود المنتج",
            "المنتج",
            "الفئة",
            "المورد الأساسي",
            "الوحدة",
            "الكمية الحالية",
            "تكلفة الوحدة الحالية",
            "قيمة المخزون الراكد",
            "تاريخ أول دخول",
            "تاريخ آخر دخول",
            "تاريخ آخر تسليم",
            "أيام الركود",
            "الكمية المباعة خلال الفترة",
            "مرتجعات العملاء خلال الفترة",
            "صافي كمية مبيعات المنتج خلال الفترة",
            "الحالة",
        ]
        widths = [15, 36, 24, 26, 12, 15, 18, 20, 16, 16, 16, 13, 21, 21, 15, 18]
        worksheet.merge_range(0, 0, 0, len(headers) - 1, "تقرير المنتجات الراكدة", title_format)
        worksheet.write(1, 0, "الشركة", label_format)
        worksheet.write(1, 1, self.company_id.display_name, cell_format)
        worksheet.write(1, 2, "تاريخ التقرير", label_format)
        worksheet.write(1, 3, str(self.report_date), cell_format)
        worksheet.write(1, 4, "مدة الركود", label_format)
        worksheet.write(1, 5, self.inactivity_days, cell_format)
        worksheet.write(1, 6, "عدد المنتجات", label_format)
        worksheet.write(1, 7, len(lines), cell_format)
        worksheet.write(1, 8, "إجمالي القيمة", label_format)
        worksheet.write_number(
            1,
            9,
            sum(line["stock_value"] for line in lines),
            money_format,
        )
        branch_names = ", ".join(self.branch_ids.mapped("display_name")) or "جميع الفروع"
        location_names = ", ".join(self.location_ids.mapped("display_name"))
        worksheet.write(2, 0, "الفروع", label_format)
        worksheet.merge_range(2, 1, 2, 4, branch_names, cell_format)
        worksheet.write(2, 5, "المواقع", label_format)
        worksheet.merge_range(2, 6, 2, 10, location_names, cell_format)
        worksheet.write(2, 11, "فترة المبيعات", label_format)
        worksheet.merge_range(
            2,
            12,
            2,
            len(headers) - 1,
            "%s إلى %s" % (self.sales_date_from, self.sales_date_to),
            cell_format,
        )
        worksheet.freeze_panes(4, 0)
        worksheet.autofilter(3, 0, 3 + len(lines), len(headers) - 1)
        for column, (header, width) in enumerate(zip(headers, widths)):
            worksheet.set_column(column, column, width)
            worksheet.write(3, column, header, header_format)

        status_labels = dict(
            self.env["eljohany.slow.moving.report.line"]._fields[
                "status"
            ].selection
        )
        for row, line in enumerate(lines, start=4):
            text_values = [
                line["default_code"],
                line["product_name"],
                line["category_name"],
                line["vendor_name"],
                line["uom_name"],
            ]
            for column, value in enumerate(text_values):
                worksheet.write(row, column, value, cell_format)
            worksheet.write_number(row, 5, line["qty_on_hand"], qty_format)
            worksheet.write_number(row, 6, line["unit_cost"], money_format)
            worksheet.write_number(row, 7, line["stock_value"], money_format)
            for column, key in (
                (8, "first_stock_date"),
                (9, "last_receipt_date"),
                (10, "last_delivery_date"),
            ):
                value = line[key]
                if value:
                    worksheet.write_datetime(
                        row,
                        column,
                        datetime.combine(value, time.min),
                        date_format,
                    )
                else:
                    worksheet.write(row, column, "لم يحدث", cell_format)
            worksheet.write_number(row, 11, line["days_inactive"], cell_format)
            worksheet.write_number(row, 12, line["qty_delivered_period"], qty_format)
            worksheet.write_number(row, 13, line["qty_returned_period"], qty_format)
            worksheet.write_number(row, 14, line["net_qty_sold_period"], qty_format)
            worksheet.write(row, 15, status_labels[line["status"]], cell_format)

        workbook.close()
        output.seek(0)
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": "Slow_Moving_Products_%s.xlsx" % self.report_date,
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


class EljohanySlowMovingReportLine(models.TransientModel):
    _name = "eljohany.slow.moving.report.line"
    _description = "Slow Moving Products Report Line"
    _order = "stock_value desc, days_inactive desc, default_code, product_name"

    wizard_id = fields.Many2one(
        "eljohany.slow.moving.report.wizard",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one("product.product", string="المنتج", readonly=True)
    default_code = fields.Char(string="كود المنتج", readonly=True)
    product_name = fields.Char(string="اسم المنتج", readonly=True)
    category_name = fields.Char(string="الفئة", readonly=True)
    uom_name = fields.Char(string="الوحدة", readonly=True)
    vendor_name = fields.Char(string="المورد الأساسي", readonly=True)
    qty_on_hand = fields.Float(string="الكمية الحالية", readonly=True, digits="Product Unit of Measure")
    unit_cost = fields.Monetary(string="تكلفة الوحدة الحالية", readonly=True)
    stock_value = fields.Monetary(string="قيمة المخزون الراكد", readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        related="wizard_id.company_id.currency_id",
        readonly=True,
    )
    first_stock_date = fields.Date(string="تاريخ أول دخول", readonly=True)
    last_receipt_date = fields.Date(string="تاريخ آخر دخول", readonly=True)
    last_delivery_date = fields.Date(string="تاريخ آخر تسليم", readonly=True)
    days_inactive = fields.Integer(string="أيام الركود", readonly=True)
    qty_delivered_period = fields.Float(
        string="الكمية المباعة خلال الفترة",
        readonly=True,
        digits="Product Unit of Measure",
    )
    qty_returned_period = fields.Float(
        string="مرتجعات العملاء خلال الفترة",
        readonly=True,
        digits="Product Unit of Measure",
    )
    net_qty_sold_period = fields.Float(
        string="صافي كمية مبيعات المنتج خلال الفترة",
        readonly=True,
        digits="Product Unit of Measure",
    )
    status = fields.Selection(
        [
            ("stagnant", "راكد"),
            ("very_stagnant", "راكد جدًا"),
            ("never_sold", "لم يُبع مطلقًا"),
        ],
        string="الحالة",
        readonly=True,
    )
