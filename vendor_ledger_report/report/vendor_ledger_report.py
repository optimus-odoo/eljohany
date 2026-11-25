from odoo import api, models


class ReportVendorLedger(models.AbstractModel):
    _name = "report.vendor_ledger_report.vendor_ledger_report_pdf"
    _description = "تقرير كشف حساب الموردين الشامل بصيغة PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard_id = data.get("wizard_id") or (docids and docids[0])
        wizard = self.env["vendor.ledger.report.wizard"].browse(wizard_id).exists()
        if not wizard:
            return {"docs": [], "partners": []}

        report_data = wizard._prepare_report_data()
        return {
            "doc_ids": wizard.ids,
            "doc_model": "vendor.ledger.report.wizard",
            "docs": wizard,
            "wizard": wizard,
            "labels": wizard._get_arabic_labels(),
            **report_data,
        }
