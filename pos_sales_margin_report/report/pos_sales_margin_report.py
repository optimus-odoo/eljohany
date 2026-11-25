from odoo import api, models


class ReportPosSalesMargin(models.AbstractModel):
    _name = "report.pos_sales_margin_report.pos_sales_margin_report_pdf"
    _description = "POS Sales and Margin PDF Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard_id = data.get("wizard_id") or (docids and docids[0])
        wizard = self.env["pos.sales.margin.report.wizard"].browse(wizard_id).exists()
        if not wizard:
            return {
                "doc_ids": [],
                "doc_model": "pos.sales.margin.report.wizard",
                "docs": wizard,
                "wizard": wizard,
                "labels": wizard._get_arabic_report_labels(),
                "date_from_display": "",
                "date_to_display": "",
                "lines": [],
                "totals": {},
                "uncomputed_cost_count": 0,
            }
        report_data = wizard._prepare_report_data()
        return {
            "doc_ids": wizard.ids,
            "doc_model": "pos.sales.margin.report.wizard",
            "docs": wizard,
            "wizard": wizard,
            "labels": wizard._get_arabic_report_labels(),
            "date_from_display": wizard._format_report_datetime(wizard.date_from),
            "date_to_display": wizard._format_report_datetime(wizard.date_to),
            **report_data,
        }
