import uuid

from odoo import fields, models


class HrAttendanceApiEvent(models.Model):
    _name = "hr.attendance.api.event"
    _description = "HR Attendance API Event"
    _order = "event_at desc, id desc"

    request_id = fields.Char(
        required=True, default=lambda self: str(uuid.uuid4()), index=True, readonly=True
    )
    idempotency_key = fields.Char(index=True, readonly=True)
    event_type = fields.Selection(
        [("check_in", "Check In"), ("check_out", "Check Out")],
        required=True,
        index=True,
        readonly=True,
    )
    period = fields.Selection(
        [("morning", "Morning"), ("evening", "Evening")],
        required=True,
        index=True,
        readonly=True,
    )
    event_at = fields.Datetime(required=True, index=True, readonly=True)
    employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="restrict", index=True, readonly=True
    )
    attendance_id = fields.Many2one(
        "hr.attendance", required=True, ondelete="restrict", index=True, readonly=True
    )
    branch_id = fields.Many2one(
        "res.branch", required=True, ondelete="restrict", index=True, readonly=True
    )
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, index=True, readonly=True
    )
    token_id = fields.Many2one(
        "hr.attendance.api.token", ondelete="set null", index=True, readonly=True
    )
    latitude = fields.Float(digits=(10, 7), readonly=True)
    longitude = fields.Float(digits=(10, 7), readonly=True)
    accuracy = fields.Float(readonly=True)
    distance = fields.Float(readonly=True)
    source_ip = fields.Char(readonly=True)

    _sql_constraints = [
        ("request_id_unique", "unique(request_id)", "The API request ID must be unique."),
        (
            "employee_idempotency_unique",
            "unique(employee_id, idempotency_key)",
            "This attendance request was already processed.",
        ),
    ]
