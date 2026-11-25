from odoo import models, fields

class ProductProduct(models.Model):
    _inherit = "product.product"

    min_sale_price = fields.Float(string="Minimum Sale Price")
