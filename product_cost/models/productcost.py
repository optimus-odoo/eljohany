from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductCost(models.Model):
    _inherit = 'product.template'

    min_cost = fields.Float(string="Minimum Price")
    max_cost = fields.Float(string="Maximum Price")

    @api.onchange('min_cost')
    def check_price(self):
        for rec in self:
            if rec.standard_price > 1 and rec.min_cost < rec.standard_price and not self.env.user.has_group('product_min_sale_price.group_ignore_min_price_warning'):
                raise ValidationError("Minimum Price can't be less than Cost Price")


class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'


class SaleOrderLineInherit(models.Model):
    _inherit = 'sale.order.line'

    min_price = fields.Float(
        string="Minimum Price",
        related='product_id.min_cost',
        store=True,
        readonly=True)
    max_price = fields.Float(
        string="Maximum Price",
        related='product_id.max_cost',
        store=True,
        readonly=True)

    @api.constrains('price_unit', 'product_id')
    def check_unit_price(self):
        for line in self:
            product = line.product_id
            if not product:
                continue
            if product.min_cost and line.price_unit < product.min_cost and not self.env.user.has_group('product_min_sale_price.group_ignore_min_price_warning'):
                raise ValidationError(
                    f"The unit price ({line.price_unit:.2f}) is less than the minimum allowed Price for Product >> {product.display_name} \n minimum allowed Price is  ({product.min_cost:.2f})."
                )

            if product.max_cost and line.price_unit > product.max_cost and not self.env.user.has_group('product_min_sale_price.group_ignore_min_price_warning'):
                raise ValidationError(
                    f"The unit price ({line.price_unit:.2f}) is greater than the maximum allowed Price  for Product >> {product.display_name}  \n maximum allowed Price is  ({product.max_cost:.2f})."
                )
