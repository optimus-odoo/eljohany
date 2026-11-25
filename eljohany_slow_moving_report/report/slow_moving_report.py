# -*- coding: utf-8 -*-

from odoo import api, models


class SlowMovingProductsReport(models.AbstractModel):
    _name = "report.eljohany_slow_moving_report.report_slow_moving_document"
    _description = "Slow Moving Products PDF Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env["eljohany.slow.moving.report.wizard"].browse(docids)
        wizard = wizards[:1]
        lines = wizard.line_ids if wizard else self.env["eljohany.slow.moving.report.line"]
        return {
            "doc_ids": wizards.ids,
            "doc_model": "eljohany.slow.moving.report.wizard",
            "docs": wizards,
            "lines": lines,
            "total_value": sum(lines.mapped("stock_value")),
        }
