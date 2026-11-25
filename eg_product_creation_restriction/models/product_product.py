from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('eg_product_creation_restriction.product_creation_restriction'):
            raise ValidationError(_("You don't have access to create product."))
        return super().create(vals_list)
