# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class SaleOrderINhnds(models.Model):
    _inherit = 'sale.order'

    is_trust = fields.Boolean(copy=False, string="امانات")
    am_seq = fields.Char(required=False, default="New", copy=False)

    def action_confirm(self):
        for rec in self:
            res = super(SaleOrderINhnds, self).action_confirm()
            if rec.is_trust:
                rec.am_seq = self.env['ir.sequence'].sudo().next_by_code('seq_sale_order_trust')
                rec.picking_ids.write({
                    'is_trust': rec.is_trust
                })
            return res


class stockPickingINh(models.Model):
    _inherit = 'stock.picking'

    is_trust = fields.Boolean(copy=False, string="امانات")
    am_seq = fields.Char(required=False, default="New", copy=False)

    def button_validate(self):
        for rec in self:
            res = super(stockPickingINh, self).button_validate()
            if rec.is_trust:
                rec.am_seq = self.env['ir.sequence'].sudo().next_by_code('seq_operation_trust')
            return res
