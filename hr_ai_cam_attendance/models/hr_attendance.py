
from odoo import models, fields, api, tools, _
import logging
_logger = logging.getLogger(__name__)
class HRAttendance(models.Model):
    _inherit = "hr.attendance"
    location = fields.Selection([('inside_location', 'Inside Location'), ('outside_location', 'Outside Location')], default='inside_location')
    # attendance_image = fields.Binary("Image", attachment=True)
    # out_attendance_image = fields.Binary(string="Out Image")
    # match = fields.Boolean()
    checkin_geolocation = fields.Char('Checkin Geolocation')
    checkout_geolocation = fields.Char('Checkout Geolocation')

    attendance_image = fields.Binary("Image", attachment=True)
    out_attendance_image = fields.Binary(string="Out Image")
