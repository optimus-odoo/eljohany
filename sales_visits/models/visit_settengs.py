# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class AttendanceConfig(models.TransientModel):
    _inherit = ['res.config.settings']

    visit_max_distance = fields.Integer()

    def set_values(self):
        super(AttendanceConfig, self).set_values()

        self.env['ir.config_parameter'].sudo().set_param(
            "sales_visits.visit_max_distance", self.visit_max_distance)

    @api.model
    def get_values(self):
        res = super(AttendanceConfig, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res['visit_max_distance'] = get_param('sales_visits.visit_max_distance')
        return res