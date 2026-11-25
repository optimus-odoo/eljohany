from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    api_branch_id = fields.Many2one("res.branch", string="API Branch", index=True)
    api_check_in_period = fields.Selection(
        [("morning", "Morning"), ("evening", "Evening")],
        string="Check-in Period",
        index=True,
    )
    api_check_out_period = fields.Selection(
        [("morning", "Morning"), ("evening", "Evening")],
        string="Check-out Period",
        index=True,
    )
    api_check_in_accuracy = fields.Float(string="Check-in GPS Accuracy (m)")
    api_check_out_accuracy = fields.Float(string="Check-out GPS Accuracy (m)")
    api_check_in_distance = fields.Float(string="Check-in Distance (m)")
    api_check_out_distance = fields.Float(string="Check-out Distance (m)")
    api_source = fields.Selection(
        [
            ("mobile_api", "Mobile API"),
            ("external_sync", "External HR Sync"),
        ],
        string="API Source",
        index=True,
    )
    api_external_id = fields.Char(
        string="External Attendance ID", index=True, copy=False
    )
    api_event_ids = fields.One2many(
        "hr.attendance.api.event", "attendance_id", string="API Events"
    )

    _sql_constraints = [
        (
            "api_external_attendance_unique",
            "unique(api_external_id)",
            "The external attendance ID must be unique.",
        )
    ]
