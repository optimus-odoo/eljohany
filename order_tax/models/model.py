from odoo import models, fields, api


class AddSeq(models.Model):
    _inherit = 'sale.order.line'

    tax_id = fields.Many2many('account.tax', readonly=False)

    @api.onchange('product_id')
    def _onchange_set_taxes(self):
        for rec in self:
            if rec.product_id:
                taxes = rec.product_id.taxes_id.filtered(lambda tax: tax.company_id == rec.order_id.company_id)
                rec.tax_id = taxes
