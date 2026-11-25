# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    shared_company_ids = fields.Many2many(
        'res.company',
        'commission_product_template_res_company_rel',
        'product_tmpl_id',
        'company_id',
        string='Shared Companies',
        help='Additional companies allowed to access this product without changing its owner company.',
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    shared_company_ids = fields.Many2many(
        related='product_tmpl_id.shared_company_ids',
        readonly=False,
    )
