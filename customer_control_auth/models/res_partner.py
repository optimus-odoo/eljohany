# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError, AccessError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            is_customer = False

            if vals.get('customer_rank', 0) > 0:
                is_customer = True

            if vals.get('company_type') in ('person', 'company') and not vals.get('supplier_rank'):
                is_customer = True

            if is_customer and not self.env.user.has_group(
                'customer_control_auth.group_allow_create_customer'
            ):
                raise AccessError(_("You are not allowed to create a new customer."))

        return super().create(vals_list)

    @api.constrains('vat', 'company_id', 'active')
    def _check_unique_vat(self):
        for rec in self:
            vat = (rec.vat or '').strip()
            if not vat:
                continue

            same_partners = self.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('vat', '!=', False),
                ('company_id', '=', rec.company_id.id),
            ])

            normalized_vat = vat.replace(' ', '').upper()

            duplicate = same_partners.filtered(
                lambda p: (p.vat or '').replace(' ', '').upper() == normalized_vat
            )

            if duplicate and not self.env.user.has_group('account.allow_duplicate_partner'):
                raise ValidationError(_(
                    "Tax/VAT number must be unique. This VAT already exists for: %s"
                ) % ', '.join(duplicate.mapped('name')))
