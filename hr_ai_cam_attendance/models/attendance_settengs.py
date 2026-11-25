# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class AttendanceConfig(models.TransientModel):
    _inherit = ['res.config.settings']

    long = fields.Char()
    lat = fields.Char()

    working_from = fields.Float()
    working_to = fields.Float()

    max_distance = fields.Integer()

    hr_attendance_face_rec = fields.Boolean()
    def set_values(self):
        super(AttendanceConfig, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            "hr_ai_cam_attendance.long", self.long)
        self.env['ir.config_parameter'].sudo().set_param(
            "hr_ai_cam_attendance.lat", self.lat)
        self.env['ir.config_parameter'].sudo().set_param(
            "hr_ai_cam_attendance.working_from", self.working_from)
        self.env['ir.config_parameter'].sudo().set_param(
            "hr_ai_cam_attendance.working_to", self.working_to)
        self.env['ir.config_parameter'].sudo().set_param(
            "hr_ai_cam_attendance.max_distance", self.max_distance)
        self.env['ir.config_parameter'].sudo().set_param(
            "hr_ai_cam_attendance.hr_attendance_face_rec", self.hr_attendance_face_rec)

    @api.model
    def get_values(self):
        res = super(AttendanceConfig, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res['long'] = float(get_param('hr_ai_cam_attendance.long'))
        res['lat'] = float(get_param('hr_ai_cam_attendance.lat'))
        res['working_from'] = float(get_param('hr_ai_cam_attendance.working_from'))
        res['working_to'] = float(get_param('hr_ai_cam_attendance.working_to'))
        res['hr_attendance_face_rec'] = get_param('hr_ai_cam_attendance.hr_attendance_face_rec')
        res['max_distance'] = get_param('hr_ai_cam_attendance.max_distance')
        return res