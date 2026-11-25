# -*- coding: utf-8 -*-
from odoo import api, models


class ReportEljohanyStockAging(models.AbstractModel):
    _name = "report.eljohany_stock_aging_report.stock_aging_report_pdf"
    _description = "Eljohany Stock Aging Report PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard_id = data.get("wizard_id") or (docids and docids[0])
        wizard = self.env["eljohany.stock.aging.report.wizard"].sudo().browse(wizard_id).exists()
        if not wizard:
            return {"docs": [], "lines": []}

        return {
            "doc_ids": wizard.ids,
            "doc_model": "eljohany.stock.aging.report.wizard",
            "docs": wizard,
            "wizard": wizard,
            "lines": wizard._prepare_lines(),
        }
