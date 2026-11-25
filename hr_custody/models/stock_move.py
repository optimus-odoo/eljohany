# -*- coding: utf-8 -*-
from odoo import models, fields


class StockMove(models.Model):
    _inherit = "stock.move"

    custody_line_id = fields.Many2one("hr.custody.line", string="Custody Line", copy=False)
