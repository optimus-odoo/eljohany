# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import http, _
from odoo.http import request



class AttendanceFaceRecognitionController(http.Controller):

    @http.route('/face_recognition/save_attendance', type='json', auth='user')
    def face_recognition_save_attendance(self, payload):
        """ Receive a payload scanned from the main menu and return the appropriate
            action (open an existing / new picking) or warning.
        """
        employee = request.env.user.sudo().employee_id
        if not payload.get('location', False):
            return False
        location = payload.get('location', False)
        image_bytes = payload.get('image_bytes', False)
        res = employee.sudo().with_context(loc=location, image_bytes=image_bytes)._attendance_action_change()
        return res
