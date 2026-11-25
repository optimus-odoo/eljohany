# -*- coding: utf-8 -*-
from odoo import api, models


class ReportStockItemStatus(models.AbstractModel):
    _name = "report.stock_item_status_report.stock_item_status_report_pdf"
    _description = "Stock Item Status Report PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard_id = data.get("wizard_id") or (docids and docids[0])
        wizard = self.env["stock.item.status.report.wizard"].sudo().browse(wizard_id).exists()
        if not wizard:
            return {"docs": [], "lines": []}

        lines = wizard._prepare_lines()
        return {
            "doc_ids": wizard.ids,
            "doc_model": "stock.item.status.report.wizard",
            "docs": wizard,
            "wizard": wizard,
            "lines": lines,
        }
