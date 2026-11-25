import base64
import io
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - تظهر رسالة واضحة للمستخدم عند التصدير
    xlsxwriter = None


class VendorLedgerReportWizard(models.TransientModel):
    _name = "vendor.ledger.report.wizard"
    _description = "معالج كشف حساب الموردين الشامل"

    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self.env.company,
    )
    show_all_suppliers = fields.Boolean(
        string="إظهار جميع الموردين",
        help="عدم تقييد التقرير بمورد محدد وإظهار كشف مستقل لكل مورد.",
    )
    display_mode = fields.Selection(
        [
            ("details", "تفصيلي - إظهار القيود"),
            ("summary", "ملخص - إظهار الإجماليات فقط"),
        ],
        string="خيار عرض التقرير",
        required=True,
        default="details",
        help=(
            "اختر العرض التفصيلي لإظهار القيود، أو العرض الملخص لإظهار الرصيد "
            "الافتتاحي وإجمالي حركة الفترة والرصيد الختامي فقط."
        ),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="المورد",
        check_company=True,
        domain="[('supplier_rank', '>', 0), ('company_id', 'in', [False, company_id])]",
    )
    date_from = fields.Date(
        string="من تاريخ",
        required=True,
        default=_default_date_from,
    )
    date_to = fields.Date(
        string="إلى تاريخ",
        required=True,
        default=fields.Date.context_today,
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wizard in self:
            if (
                wizard.partner_id
                and wizard.partner_id.company_id
                and wizard.partner_id.company_id != wizard.company_id
            ):
                wizard.partner_id = False

    @api.onchange("show_all_suppliers")
    def _onchange_show_all_suppliers(self):
        for wizard in self:
            if wizard.show_all_suppliers:
                wizard.partner_id = False

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _("يجب أن يكون تاريخ البداية سابقًا لتاريخ النهاية أو مساويًا له.")
                )

    def _validate_report_options(self):
        self.ensure_one()
        self._check_date_range()
        if self.company_id not in self.env.user.company_ids:
            raise AccessError(_("غير مسموح لك بإصدار التقرير للشركة المحددة."))
        if not self.show_all_suppliers and not self.partner_id:
            raise UserError(_("اختر موردًا أو فعّل خيار إظهار جميع الموردين."))

    def _get_target_partners(self):
        """إرجاع الموردين التجاريين المشمولين بالتقرير دون تكرار."""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id.commercial_partner_id

        suppliers = self.env["res.partner"].with_context(active_test=False).search(
            [
                ("supplier_rank", ">", 0),
                ("company_id", "in", [False, self.company_id.id]),
            ]
        )
        return suppliers.mapped("commercial_partner_id")

    def _get_base_line_domain(self, commercial_partners):
        """بنود القيود المرحلة ذات المبالغ من جميع حسابات الموردين."""
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("partner_id.commercial_partner_id", "in", commercial_partners.ids),
            ("display_type", "not in", ["line_section", "line_note"]),
            "|",
            ("debit", "!=", 0.0),
            ("credit", "!=", 0.0),
        ]

    def _get_grouped_amounts_by_partner(self, line_model, domain):
        self.ensure_one()
        groups = line_model.read_group(
            domain,
            ["partner_id", "debit:sum", "credit:sum"],
            ["partner_id"],
            lazy=False,
        )
        amounts_by_partner = defaultdict(lambda: {"debit": 0.0, "credit": 0.0})
        partner_ids = [group["partner_id"][0] for group in groups if group.get("partner_id")]
        commercial_by_partner = {
            partner.id: partner.commercial_partner_id.id
            for partner in self.env["res.partner"].browse(partner_ids)
        }
        for group in groups:
            partner_value = group.get("partner_id")
            if not partner_value:
                continue
            commercial_id = commercial_by_partner.get(partner_value[0])
            if not commercial_id:
                continue
            amounts_by_partner[commercial_id]["debit"] += group.get("debit") or 0.0
            amounts_by_partner[commercial_id]["credit"] += group.get("credit") or 0.0
        return amounts_by_partner

    def _get_opening_by_partner(self, line_model, base_domain):
        self.ensure_one()
        return self._get_grouped_amounts_by_partner(
            line_model,
            base_domain + [("date", "<", self.date_from)],
        )

    def _get_period_amounts_by_partner(self, line_model, base_domain):
        self.ensure_one()
        return self._get_grouped_amounts_by_partner(
            line_model,
            base_domain
            + [
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
            ],
        )

    def _line_item_name(self, line):
        name = (line.name or "").strip()
        if name and name != "/":
            return name
        return (line.move_id.ref or line.move_id.name or "").strip()

    def _line_to_dict(self, line, running_balance):
        move = line.move_id
        document_date = move.invoice_date or move.date
        return {
            "id": line.id,
            "date": line.date,
            "date_display": fields.Date.to_string(line.date),
            "document_date": document_date,
            "document_date_display": fields.Date.to_string(document_date),
            "document": move.name or "/",
            "reference": move.ref or "",
            "journal": line.journal_id.display_name,
            "account": "%s %s"
            % (line.account_id.code or "", line.account_id.name or ""),
            "item": self._line_item_name(line),
            "debit": line.debit,
            "credit": line.credit,
            "balance": line.balance,
            "running_balance": running_balance,
        }

    def _build_partner_report(
        self, partner, opening_values, move_lines=(), period_values=None
    ):
        self.ensure_one()
        opening_debit = opening_values.get("debit", 0.0)
        opening_credit = opening_values.get("credit", 0.0)
        opening_balance = opening_debit - opening_credit
        running_balance = opening_balance
        lines = []
        if period_values is None:
            period_debit = 0.0
            period_credit = 0.0
            for move_line in move_lines:
                period_debit += move_line.debit
                period_credit += move_line.credit
                running_balance += move_line.balance
                lines.append(self._line_to_dict(move_line, running_balance))
        else:
            period_debit = period_values.get("debit", 0.0)
            period_credit = period_values.get("credit", 0.0)
            running_balance += period_debit - period_credit

        return {
            "partner": partner,
            "partner_name": partner.display_name,
            "vat": partner.vat or "",
            "opening_debit": max(opening_balance, 0.0),
            "opening_credit": max(-opening_balance, 0.0),
            "opening_balance": opening_balance,
            "period_debit": period_debit,
            "period_credit": period_credit,
            "closing_balance": running_balance,
            "closing_debit": max(running_balance, 0.0),
            "closing_credit": max(-running_balance, 0.0),
            "lines": lines,
        }

    def _prepare_report_data(self):
        self.ensure_one()
        self._validate_report_options()
        commercial_partners = self._get_target_partners()
        if not commercial_partners:
            return {"partners": [], "supplier_count": 0, "line_count": 0}

        line_model = self.env["account.move.line"].with_company(self.company_id)
        base_domain = self._get_base_line_domain(commercial_partners)
        opening_by_partner = self._get_opening_by_partner(line_model, base_domain)
        detailed_mode = self.display_mode == "details"
        lines_by_partner = defaultdict(list)
        period_amounts_by_partner = {}
        if detailed_mode:
            period_lines = line_model.search(
                base_domain
                + [
                    ("date", ">=", self.date_from),
                    ("date", "<=", self.date_to),
                ],
                order="date, move_name, id",
            )
            for line in period_lines:
                commercial_id = line.partner_id.commercial_partner_id.id
                lines_by_partner[commercial_id].append(line)
        else:
            period_amounts_by_partner = self._get_period_amounts_by_partner(
                line_model, base_domain
            )

        if self.show_all_suppliers:
            partner_ids = (
                set(lines_by_partner)
                | set(period_amounts_by_partner)
                | set(opening_by_partner)
            )
        else:
            partner_ids = set(commercial_partners.ids)

        currency = self.company_id.currency_id
        partner_reports = []
        for partner in commercial_partners.filtered(lambda item: item.id in partner_ids).sorted(
            lambda item: (item.display_name or "").casefold()
        ):
            opening_values = opening_by_partner.get(
                partner.id, {"debit": 0.0, "credit": 0.0}
            )
            move_lines = lines_by_partner.get(partner.id, ())
            period_values = period_amounts_by_partner.get(
                partner.id, {"debit": 0.0, "credit": 0.0}
            )
            opening_balance = opening_values["debit"] - opening_values["credit"]
            has_period_activity = bool(move_lines) or not (
                currency.is_zero(period_values["debit"])
                and currency.is_zero(period_values["credit"])
            )
            if (
                self.show_all_suppliers
                and not has_period_activity
                and currency.is_zero(opening_balance)
            ):
                continue
            partner_reports.append(
                self._build_partner_report(
                    partner,
                    opening_values,
                    move_lines,
                    period_values=None if detailed_mode else period_values,
                )
            )

        return {
            "partners": partner_reports,
            "supplier_count": len(partner_reports),
            "line_count": sum(len(report["lines"]) for report in partner_reports),
        }

    def _get_arabic_labels(self):
        return {
            "title": "كشف حساب الموردين الشامل",
            "company": "الشركة",
            "currency": "العملة",
            "period": "الفترة",
            "to": "إلى",
            "supplier": "المورد",
            "all_suppliers": "جميع الموردين",
            "vat": "الرقم الضريبي",
            "accounting_date": "تاريخ القيد",
            "document_date": "تاريخ الفاتورة / المستند",
            "document": "رقم القيد / الفاتورة",
            "journal": "اليومية",
            "account": "الحساب",
            "item": "اسم البند / البيان",
            "debit": "مدين",
            "credit": "دائن",
            "balance": "الرصيد",
            "description": "البيان",
            "opening": "الرصيد الافتتاحي قبل بداية الفترة",
            "period_total": "إجمالي حركة الفترة",
            "closing": "الرصيد الختامي",
            "display_mode": "خيار عرض التقرير",
            "details": "تفصيلي - إظهار القيود",
            "summary_only": "ملخص - إظهار الإجماليات فقط",
            "posted_only": "يشمل التقرير القيود المرحلة فقط، ومن جميع أنواع الحسابات المرتبطة بالمورد. الرصيد الموجب مدين والرصيد السالب دائن.",
            "no_data": "لا توجد قيود مرحلة مطابقة للخيارات المحددة.",
        }

    def action_view_report(self):
        self.ensure_one()
        self._validate_report_options()
        return self.env.ref(
            "vendor_ledger_report.action_vendor_ledger_report_html"
        ).report_action(self, data={"wizard_id": self.id})

    def action_print_pdf(self):
        self.ensure_one()
        self._validate_report_options()
        return self.env.ref(
            "vendor_ledger_report.action_vendor_ledger_report_pdf"
        ).report_action(self, data={"wizard_id": self.id})

    def action_export_excel(self):
        self.ensure_one()
        self._validate_report_options()
        if not xlsxwriter:
            raise UserError(_("مكتبة xlsxwriter مطلوبة لتصدير ملف Excel."))

        report_data = self._prepare_report_data()
        labels = self._get_arabic_labels()
        detailed_mode = self.display_mode == "details"
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        worksheet = workbook.add_worksheet("كشف الموردين")
        worksheet.right_to_left()
        worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
        worksheet.set_margins(0.25, 0.25, 0.5, 0.5)
        worksheet.set_column(0, 1, 16)
        worksheet.set_column(2, 2, 22)
        worksheet.set_column(3, 4, 20)
        worksheet.set_column(5, 5, 40)
        worksheet.set_column(6, 8, 16)

        title_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 16,
                "font_color": "#FFFFFF",
                "bg_color": "#1F4E78",
                "align": "center",
                "valign": "vcenter",
            }
        )
        meta_format = workbook.add_format(
            {"bold": True, "align": "right", "valign": "vcenter"}
        )
        note_format = workbook.add_format(
            {
                "font_color": "#665200",
                "bg_color": "#FFF2CC",
                "align": "right",
            }
        )
        partner_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "font_color": "#FFFFFF",
                "bg_color": "#4472C4",
                "align": "right",
            }
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "bg_color": "#D9EAF7",
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        text_format = workbook.add_format(
            {"border": 1, "align": "right", "valign": "vcenter"}
        )
        date_format = workbook.add_format(
            {"border": 1, "align": "center", "num_format": "yyyy-mm-dd"}
        )
        amount_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "num_format": "#,##0.00;[Red]-#,##0.00",
            }
        )
        summary_label_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "bg_color": "#E2F0D9",
                "align": "right",
            }
        )
        summary_amount_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "bg_color": "#E2F0D9",
                "align": "center",
                "num_format": "#,##0.00;[Red]-#,##0.00",
            }
        )

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
            "%s: %s %s %s | %s: %s | %s: %s"
            % (
                labels["period"],
                fields.Date.to_string(self.date_from),
                labels["to"],
                fields.Date.to_string(self.date_to),
                labels["supplier"],
                self.partner_id.commercial_partner_id.display_name
                if self.partner_id
                else labels["all_suppliers"],
                labels["display_mode"],
                labels["details"] if detailed_mode else labels["summary_only"],
            ),
            meta_format,
        )
        worksheet.merge_range(3, 0, 3, 8, labels["posted_only"], note_format)

        headers = [
            labels["accounting_date"],
            labels["document_date"],
            labels["document"],
            labels["journal"],
            labels["account"],
            labels["item"],
            labels["debit"],
            labels["credit"],
            labels["balance"],
        ]
        row = 5
        for partner_report in report_data["partners"]:
            partner_heading = "%s: %s" % (
                labels["supplier"],
                partner_report["partner_name"],
            )
            if partner_report["vat"]:
                partner_heading += " | %s: %s" % (
                    labels["vat"],
                    partner_report["vat"],
                )
            worksheet.merge_range(row, 0, row, 8, partner_heading, partner_format)
            row += 1
            if detailed_mode:
                for column, header in enumerate(headers):
                    worksheet.write(row, column, header, header_format)
            else:
                worksheet.merge_range(
                    row, 0, row, 5, labels["description"], header_format
                )
                worksheet.write(row, 6, labels["debit"], header_format)
                worksheet.write(row, 7, labels["credit"], header_format)
                worksheet.write(row, 8, labels["balance"], header_format)
            row += 1
            worksheet.merge_range(row, 0, row, 5, labels["opening"], summary_label_format)
            worksheet.write_number(row, 6, partner_report["opening_debit"], summary_amount_format)
            worksheet.write_number(row, 7, partner_report["opening_credit"], summary_amount_format)
            worksheet.write_number(row, 8, partner_report["opening_balance"], summary_amount_format)
            row += 1

            if detailed_mode:
                for line in partner_report["lines"]:
                    worksheet.write_datetime(row, 0, line["date"], date_format)
                    worksheet.write_datetime(
                        row, 1, line["document_date"], date_format
                    )
                    worksheet.write(row, 2, line["document"], text_format)
                    worksheet.write(row, 3, line["journal"], text_format)
                    worksheet.write(row, 4, line["account"], text_format)
                    worksheet.write(row, 5, line["item"], text_format)
                    worksheet.write_number(row, 6, line["debit"], amount_format)
                    worksheet.write_number(row, 7, line["credit"], amount_format)
                    worksheet.write_number(
                        row, 8, line["running_balance"], amount_format
                    )
                    row += 1

            worksheet.merge_range(row, 0, row, 5, labels["period_total"], summary_label_format)
            worksheet.write_number(row, 6, partner_report["period_debit"], summary_amount_format)
            worksheet.write_number(row, 7, partner_report["period_credit"], summary_amount_format)
            worksheet.write_number(
                row,
                8,
                partner_report["period_debit"] - partner_report["period_credit"],
                summary_amount_format,
            )
            row += 1
            worksheet.merge_range(row, 0, row, 7, labels["closing"], summary_label_format)
            worksheet.write_number(row, 8, partner_report["closing_balance"], summary_amount_format)
            row += 2

        if not report_data["partners"]:
            worksheet.merge_range(row, 0, row, 8, labels["no_data"], note_format)

        worksheet.freeze_panes(5, 0)
        worksheet.print_area(0, 0, max(row, 5), 8)
        workbook.close()
        output.seek(0)

        filename = "كشف_حساب_الموردين_%s_%s.xlsx" % (
            self.date_from.strftime("%Y%m%d"),
            self.date_to.strftime("%Y%m%d"),
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
