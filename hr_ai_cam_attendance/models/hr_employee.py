import math
import re
from datetime import datetime

import pytz
from odoo import models, fields, api, tools, _
from odoo.http import request
import base64
import logging
import time
_logger = logging.getLogger(__name__)
class HREmployee(models.Model):
    _inherit = "hr.employee"

    employee_latitude = fields.Float(string='Geo Latitude', digits=(10, 7))
    employee_longitude = fields.Float(string='Geo Longitude', digits=(10, 7))

    attendance_location = fields.Selection([('inside_company', 'Inside Company'), ('employee_location', 'Employee Location'), ('any', 'Any location')], default='inside_company')

    def _attendance_action_change(self, geo_information=None):
        attendance_state = self.attendance_state
        location = self._context.get('loc')
        image_bytes = self._context.get('image_bytes')
        current_latitude, current_longitude = self.extract_lat_lng(location)
        attendance_location = self.env.user.employee_id.attendance_location
        location = 'outside_location'
        if attendance_location != 'any':
            if attendance_location == 'inside_company':
                longitude = float(self.env['ir.config_parameter'].sudo().get_param('hr_ai_cam_attendance.long'))
                latitude = float(self.env['ir.config_parameter'].sudo().get_param('hr_ai_cam_attendance.lat'))
            else:
                longitude = self.env.user.employee_id.employee_longitude
                latitude = self.env.user.employee_id.employee_latitude

            max_distance = float(self.env['ir.config_parameter'].sudo().get_param('hr_ai_cam_attendance.max_distance'))
            distance_to_company_m = self.calculate_distance(current_latitude, current_longitude, latitude, longitude)
            if distance_to_company_m <= max_distance:
                location = 'inside_location'

        res = super(HREmployee, self)._attendance_action_change(geo_information)

        if attendance_state != 'checked_in':
            res.write({'checkin_geolocation': self._context.get('loc', res.checkin_geolocation), 'in_latitude': current_latitude, 'in_longitude': current_longitude, 'location': location, 'attendance_image': image_bytes})
        else:
            res.write({'checkout_geolocation': self._context.get('loc', res.checkout_geolocation), 'out_latitude': current_latitude, 'out_longitude': current_longitude, 'location': location if res.location == 'inside_location' else 'outside_location', 'out_attendance_image': image_bytes})
        return res

    def calculate_distance(self,lat1, lon1, lat2, lon2):
        # Radius of the Earth in kilometers
        R = 6371

        # Convert latitude and longitude to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Calculate the differences between coordinates
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Haversine formula
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        # Calculate the distance in Meter
        distance = R * c * 1000

        return distance

    def extract_lat_lng(self, url):
        # Regular expression to match latitude and longitude
        pattern = r"place/([+-]?\d+\.\d+),([+-]?\d+\.\d+)"
        match = re.search(pattern, url)
        if match:
            latitude = float(match.group(1))
            longitude = float(match.group(2))
            return latitude, longitude
        else:
            return None, None
