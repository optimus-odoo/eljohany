# # -*- coding: utf-8 -*-
# from odoo import api, models, _
# from odoo.exceptions import AccessError


# class ProductTemplate(models.Model):
#     _inherit = "product.template"

#     def _get_cost_protected_fields(self):
#         return {"standard_price"}

#     def _check_can_edit_cost_fields(self, vals):
#         protected_fields = self._get_cost_protected_fields()
#         changed_fields = set(vals.keys()).intersection(protected_fields)

#         if changed_fields and not self.env.user.has_group("product_cost_security.group_product_cost_edit"):
#             labels = []
#             for field_name in sorted(changed_fields):
#                 field = self._fields.get(field_name)
#                 labels.append(field.string if field else field_name)

#             raise AccessError(_(
#                 "You are not allowed to modify product cost fields: %s. "
#                 "Please contact your administrator."
#             ) % ", ".join(labels))

#     def write(self, vals):
#         self._check_can_edit_cost_fields(vals)
#         return super().write(vals)

#     @api.model_create_multi
#     def create(self, vals_list):
#         for vals in vals_list:
#             self._check_can_edit_cost_fields(vals)
#         return super().create(vals_list)


# class ProductProduct(models.Model):
#     _inherit = "product.product"

#     def _get_cost_protected_fields(self):
#         return {"standard_price"}

#     def _check_can_edit_cost_fields(self, vals):
#         protected_fields = self._get_cost_protected_fields()
#         changed_fields = set(vals.keys()).intersection(protected_fields)

#         if changed_fields and not self.env.user.has_group("product_cost_security.group_product_cost_edit"):
#             labels = []
#             for field_name in sorted(changed_fields):
#                 field = self._fields.get(field_name)
#                 labels.append(field.string if field else field_name)

#             raise AccessError(_(
#                 "You are not allowed to modify product cost fields: %s. "
#                 "Please contact your administrator."
#             ) % ", ".join(labels))

#     def write(self, vals):
#         self._check_can_edit_cost_fields(vals)
#         return super().write(vals)

#     @api.model_create_multi
#     def create(self, vals_list):
#         for vals in vals_list:
#             self._check_can_edit_cost_fields(vals)
#         return super().create(vals_list)


# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import AccessError
from lxml import etree


SALE_COST_VIEW_GROUP = "product_cost_security.group_sale_order_cost_view"


class ProductCostSecurityMixin(models.AbstractModel):
    _name = "product.cost.security.mixin"
    _description = "Product Cost Security Mixin"

    @api.model
    def _get_cost_protected_fields(self):
        return {"standard_price"}

    def _check_can_edit_cost_fields(self, vals):
        current_model = self.env.context.get("current_cost_model")

        if current_model not in ("product.template", "product.product"):
            return

        changed_fields = set(vals.keys()).intersection(
            self._get_cost_protected_fields()
        )

        if not changed_fields:
            return

        if self.env.user.has_group("product_cost_security.group_product_cost_edit"):
            return

        raise AccessError(_(
            "You are not allowed to modify product cost from %s."
        ) % current_model)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        current_model = self.env.context.get("active_model")

        self.env["product.cost.security.mixin"].with_context(
            current_cost_model=current_model
        )._check_can_edit_cost_fields(vals)

        return super().write(vals)

    # @api.model_create_multi
    # def create(self, vals_list):
    #     current_model = self.env.context.get("active_model")

    #     checker = self.env["product.cost.security.mixin"].with_context(
    #         current_cost_model=current_model
    #     )

    #     for vals in vals_list:
    #         checker._check_can_edit_cost_fields(vals)

    #     return super().create(vals_list)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def write(self, vals):
        current_model = self.env.context.get("active_model")

        self.env["product.cost.security.mixin"].with_context(
            current_cost_model=current_model
        )._check_can_edit_cost_fields(vals)

        return super().write(vals)

    # @api.model_create_multi
    # def create(self, vals_list):
    #     current_model = self.env.context.get("active_model")

    #     checker = self.env["product.cost.security.mixin"].with_context(
    #         current_cost_model=current_model
    #     )

    #     for vals in vals_list:
    #         checker._check_can_edit_cost_fields(vals)

    #     return super().create(vals_list)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if self.env.user.has_group(SALE_COST_VIEW_GROUP) or not result.get("arch"):
            return result

        arch = etree.fromstring(result["arch"])
        for field_node in arch.xpath("//field[@name='purchase_price']"):
            if field_node.xpath("ancestor::tree | ancestor::list"):
                field_node.set("column_invisible", "1")
            else:
                field_node.set("invisible", "1")
        result["arch"] = etree.tostring(arch, encoding="unicode")
        return result
