#!/usr/bin/python
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class Partner(models.Model):
    _name = "res.partner"
    _inherit = "res.partner"
    building_no = fields.Char(string="Building no", help="Building No")
    district = fields.Char(string="District", help="District")
    code = fields.Char(string="Code", help="Code")
    additional_no = fields.Char(string="Additional no", help="Additional No")
    other_id = fields.Char(string="Other ID", help="Other ID")
    one_time_customer = fields.Boolean()

    def test(self):
        pass


class SaleOrderInh(models.Model):
    _inherit = 'sale.order'

    one_time_customer = fields.Boolean(related="partner_id.one_time_customer")
    one_time_name = fields.Char(required=False, copy=False, string="Name")
    one_time_phone = fields.Char(required=False, copy=False, string="Phone")

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        values['one_time_customer'] = self.one_time_customer
        values['one_time_name'] = self.one_time_name
        values['one_time_phone'] = self.one_time_phone
        return values


class AccountMoveInh(models.Model):
    _inherit = 'account.move'

    one_time_customer = fields.Boolean()
    one_time_name = fields.Char(required=False, copy=False, string="Name")
    one_time_phone = fields.Char(required=False, copy=False, string="Phone")
