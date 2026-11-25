# -*- coding: utf-8 -*-
'''
model tender item
'''
from odoo import models, fields, api, _

class TenderItem(models.Model):
    _name = 'tender.item'
    _description = 'tender.item'
    _rec_name = "name"

    name = fields.Char(string=_("Name"))
    job_id = fields.Many2one('tender.job', string=_("Related Job"))
    image = fields.Image(string=_("Image"))
    uom_id = fields.Many2one('uom.uom', string=_("Unit Of Measure"))
    code = fields.Char(string=_("Code"))
    repeated = fields.Boolean(string=_('Repeated'), help='Repeated', copy=True, default=False)
    analytic_tag = fields.Many2many('account.account.tag', string=_('Analytic Tag'))
    related_product_id = fields.Many2one('product.product', string=_('Related Product'), readonly=True)

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', _('Code must be unique')),
        ('unique_name', 'UNIQUE(name)', _('Name must be unique')),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Create tender items and their related service products in batches."""
        tender_items = super().create(vals_list)
        products = self.env['product.product'].create([
            {
                'name': tender_item.name,
                'detailed_type': 'service',
            }
            for tender_item in tender_items
        ])
        for tender_item, product in zip(tender_items, products):
            tender_item.related_product_id = product
        return tender_items

    def unlink(self):
        """
        Delete the current record if its state is 'draft'.
        """
        for tender_item in self:
            if tender_item.related_product_id:
                tender_item.related_product_id.active = False
        return super(TenderItem, self).unlink()
