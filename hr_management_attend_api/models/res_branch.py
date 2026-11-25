import math

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResBranch(models.Model):
    _inherit = "res.branch"

    active = fields.Boolean(default=True)
    api_attendance_enabled = fields.Boolean(
        string="API Attendance Enabled",
        default=False,
    )
    api_external_id = fields.Char(string="External HR Branch ID", index=True, copy=False)
    api_enforce_time_windows = fields.Boolean(
        string="Enforce Attendance Windows",
        default=False,
        help="When enabled, check-in is accepted only inside the selected period window.",
    )
    api_latitude = fields.Float(string="GPS Latitude", digits=(10, 7))
    api_longitude = fields.Float(string="GPS Longitude", digits=(10, 7))
    api_radius_m = fields.Float(string="Allowed Radius (m)", default=150.0)
    api_max_accuracy_m = fields.Float(
        string="Maximum GPS Accuracy (m)", default=100.0
    )
    api_timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
        string="Attendance Timezone",
        default=lambda self: self.env.user.tz or "UTC",
        required=True,
    )
    api_morning_start = fields.Float(string="Morning Start", default=8.0)
    api_morning_end = fields.Float(string="Morning End", default=9.0)
    api_evening_start = fields.Float(string="Evening Start", default=17.0)
    api_evening_end = fields.Float(string="Evening End", default=18.0)
    api_grace_period_minutes = fields.Integer(string="Grace Period (minutes)", default=15)

    _sql_constraints = [
        (
            "api_external_branch_company_unique",
            "unique(company_id, api_external_id)",
            "The external HR branch ID must be unique per company.",
        )
    ]

    def write(self, vals):
        sensitive_fields = {
            "active",
            "api_attendance_enabled",
            "api_latitude",
            "api_longitude",
            "api_radius_m",
            "api_max_accuracy_m",
            "api_timezone",
        }
        for branch in self:
            changed = any(
                field_name in vals and branch[field_name] != vals[field_name]
                for field_name in sensitive_fields
            )
            if changed and self.env["hr.attendance"].sudo().search_count(
                [("api_branch_id", "=", branch.id), ("check_out", "=", False)]
            ):
                raise ValidationError(
                    _("Branch attendance settings cannot change while employees are checked in.")
                )
        result = super().write(vals)
        deactivating = (
            ("active" in vals and not vals["active"])
            or ("api_attendance_enabled" in vals and not vals["api_attendance_enabled"])
        )
        if deactivating:
            tokens = self.env["hr.attendance.api.token"].sudo().search(
                [
                    ("employee_id.api_branch_id", "in", self.ids),
                    ("revoked_at", "=", False),
                ]
            )
            if tokens:
                tokens.write({"revoked_at": fields.Datetime.now()})
        return result

    @api.constrains(
        "api_latitude",
        "api_longitude",
        "api_radius_m",
        "api_max_accuracy_m",
        "api_morning_start",
        "api_morning_end",
        "api_evening_start",
        "api_evening_end",
        "api_grace_period_minutes",
    )
    def _check_api_attendance_configuration(self):
        for branch in self:
            numeric_values = (
                branch.api_latitude,
                branch.api_longitude,
                branch.api_radius_m,
                branch.api_max_accuracy_m,
                branch.api_morning_start,
                branch.api_morning_end,
                branch.api_evening_start,
                branch.api_evening_end,
            )
            if not all(math.isfinite(value) for value in numeric_values):
                raise ValidationError(_("Attendance GPS and time values must be finite numbers."))
            if not -90 <= branch.api_latitude <= 90:
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if not -180 <= branch.api_longitude <= 180:
                raise ValidationError(_("Longitude must be between -180 and 180."))
            if branch.api_radius_m <= 0:
                raise ValidationError(_("The attendance radius must be greater than zero."))
            if branch.api_max_accuracy_m <= 0:
                raise ValidationError(_("Maximum GPS accuracy must be greater than zero."))
            if branch.api_grace_period_minutes < 0:
                raise ValidationError(_("The grace period cannot be negative."))
            periods = (
                branch.api_morning_start,
                branch.api_morning_end,
                branch.api_evening_start,
                branch.api_evening_end,
            )
            if any(value < 0 or value >= 24 for value in periods):
                raise ValidationError(_("Attendance window values must be between 00:00 and 23:59."))
