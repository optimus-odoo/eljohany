from odoo import fields, models


class HrAttendanceApiSyncLog(models.Model):
    _name = "hr.attendance.api.sync.log"
    _description = "HR Attendance External Sync Log"
    _order = "started_at desc, id desc"

    name = fields.Char(required=True, readonly=True)
    company_id = fields.Many2one(
        "res.company", required=True, index=True, readonly=True
    )
    state = fields.Selection(
        [
            ("running", "Running"),
            ("success", "Successful"),
            ("partial", "Partially Successful"),
            ("failed", "Failed"),
            ("skipped", "Skipped (Already Running)"),
        ],
        required=True,
        default="running",
        index=True,
        readonly=True,
    )
    trigger = fields.Selection(
        [("manual", "Manual"), ("cron", "Scheduled")],
        required=True,
        readonly=True,
    )
    date_from = fields.Date(readonly=True)
    date_to = fields.Date(readonly=True)
    branch_id = fields.Many2one("res.branch", readonly=True)
    employee_id = fields.Many2one("hr.employee", readonly=True)
    shift = fields.Selection(
        [("morning", "Morning"), ("evening", "Evening")], readonly=True
    )
    started_at = fields.Datetime(required=True, readonly=True)
    finished_at = fields.Datetime(readonly=True)
    fetched_count = fields.Integer(readonly=True)
    created_count = fields.Integer(readonly=True)
    updated_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    branch_count = fields.Integer(readonly=True)
    employee_count = fields.Integer(readonly=True)
    message = fields.Text(readonly=True)
