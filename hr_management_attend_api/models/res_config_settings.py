from datetime import timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    attendance_api_admin_token_hours = fields.Integer(
        string="Admin Token Lifetime (hours)",
        config_parameter="hr_management_attend_api.admin_token_hours",
        default=12,
    )
    attendance_api_employee_token_hours = fields.Integer(
        string="Employee Token Lifetime (hours)",
        config_parameter="hr_management_attend_api.employee_token_hours",
        default=24,
    )
    attendance_api_max_page_size = fields.Integer(
        string="Maximum API Page Size",
        config_parameter="hr_management_attend_api.max_page_size",
        default=200,
    )
    attendance_api_allowed_origins = fields.Char(
        string="Allowed Browser Origins",
        config_parameter="hr_management_attend_api.allowed_origins",
        help="Comma-separated HTTPS origins allowed to call the API from a browser.",
    )
    attendance_api_source_enabled = fields.Boolean(
        string="Enable Scheduled External Pull",
        config_parameter="hr_management_attend_api.source_auto_sync",
        groups="base.group_system",
    )
    attendance_api_source_base_url = fields.Char(
        string="External HR API URL",
        config_parameter="hr_management_attend_api.source_base_url",
        default="https://hr2.sitksa-eg.com/api",
        groups="base.group_system",
    )
    attendance_api_source_admin_email = fields.Char(
        string="External Administrator Email",
        config_parameter="hr_management_attend_api.source_admin_email",
        groups="base.group_system",
    )
    attendance_api_source_admin_password = fields.Char(
        string="External Administrator Password",
        groups="base.group_system",
        help="Write-only. Leave blank to keep the currently stored password.",
    )
    attendance_api_source_admin_token = fields.Char(
        string="External Bearer Token",
        groups="base.group_system",
        help="Write-only and optional. If absent or expired, Odoo uses the stored email and password.",
    )
    attendance_api_source_company_id = fields.Many2one(
        "res.company",
        string="Target Odoo Company",
        config_parameter="hr_management_attend_api.source_company_id",
        default=lambda self: self.env.company,
        groups="base.group_system",
    )
    attendance_api_source_timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
        string="External System Timezone",
        config_parameter="hr_management_attend_api.source_timezone",
        default="Asia/Riyadh",
        required=True,
        groups="base.group_system",
    )
    attendance_api_source_verify_ssl = fields.Boolean(
        string="Verify TLS Certificate",
        config_parameter="hr_management_attend_api.source_verify_ssl",
        default=True,
        groups="base.group_system",
    )
    attendance_api_source_timeout_seconds = fields.Integer(
        string="Connection Timeout (seconds)",
        config_parameter="hr_management_attend_api.source_timeout_seconds",
        default=20,
        groups="base.group_system",
    )
    attendance_api_source_retry_attempts = fields.Integer(
        string="Request Retry Attempts",
        config_parameter="hr_management_attend_api.source_retry_attempts",
        default=3,
        groups="base.group_system",
    )
    attendance_api_source_page_size = fields.Integer(
        string="External Page Size",
        config_parameter="hr_management_attend_api.source_page_size",
        default=200,
        groups="base.group_system",
    )
    attendance_api_source_lookback_days = fields.Integer(
        string="Scheduled Lookback (days)",
        config_parameter="hr_management_attend_api.source_lookback_days",
        default=2,
        groups="base.group_system",
    )
    attendance_api_source_interval_minutes = fields.Integer(
        string="Scheduled Interval (minutes)",
        config_parameter="hr_management_attend_api.source_interval_minutes",
        default=15,
        groups="base.group_system",
    )
    attendance_api_source_sync_branches = fields.Boolean(
        string="Match External Branches",
        config_parameter="hr_management_attend_api.source_sync_branches",
        default=True,
        groups="base.group_system",
    )
    attendance_api_source_sync_employees = fields.Boolean(
        string="Match External Employees",
        config_parameter="hr_management_attend_api.source_sync_employees",
        default=True,
        groups="base.group_system",
    )
    attendance_api_source_create_missing_branches = fields.Boolean(
        string="Create Missing Branches",
        config_parameter="hr_management_attend_api.source_create_missing_branches",
        default=False,
        groups="base.group_system",
    )
    attendance_api_source_create_missing_employees = fields.Boolean(
        string="Create Missing Employees",
        config_parameter="hr_management_attend_api.source_create_missing_employees",
        default=False,
        groups="base.group_system",
    )
    attendance_api_source_update_reference_data = fields.Boolean(
        string="Update Matched Branches and Employees",
        config_parameter="hr_management_attend_api.source_update_reference_data",
        default=False,
        groups="base.group_system",
    )
    attendance_api_source_last_sync_at = fields.Char(
        string="Last Completed Pull",
        config_parameter="hr_management_attend_api.source_last_sync_at",
        readonly=True,
        groups="base.group_system",
    )
    attendance_api_source_last_attempt_at = fields.Char(
        string="Last Pull Attempt",
        config_parameter="hr_management_attend_api.source_last_attempt_at",
        readonly=True,
        groups="base.group_system",
    )
    attendance_api_source_last_success_at = fields.Char(
        string="Last Successful Pull",
        config_parameter="hr_management_attend_api.source_last_success_at",
        readonly=True,
        groups="base.group_system",
    )
    attendance_api_source_consecutive_failures = fields.Integer(
        string="Consecutive Pull Failures",
        config_parameter="hr_management_attend_api.source_consecutive_failures",
        readonly=True,
        groups="base.group_system",
    )
    attendance_api_sync_date_from = fields.Date(
        string="Pull From",
        default=fields.Date.context_today,
        groups="base.group_system",
    )
    attendance_api_sync_date_to = fields.Date(
        string="Pull To",
        default=fields.Date.context_today,
        groups="base.group_system",
    )
    attendance_api_sync_branch_id = fields.Many2one(
        "res.branch",
        string="External Pull Branch",
        domain="[('company_id', '=', attendance_api_source_company_id)]",
        groups="base.group_system",
    )
    attendance_api_sync_employee_id = fields.Many2one(
        "hr.employee",
        string="External Pull Employee",
        domain="[('company_id', '=', attendance_api_source_company_id), ('api_employee_number', '!=', False)]",
        groups="base.group_system",
    )
    attendance_api_sync_shift = fields.Selection(
        [("morning", "Morning"), ("evening", "Evening")],
        string="External Pull Shift",
        groups="base.group_system",
    )

    @api.constrains(
        "attendance_api_admin_token_hours",
        "attendance_api_employee_token_hours",
        "attendance_api_max_page_size",
        "attendance_api_source_timeout_seconds",
        "attendance_api_source_retry_attempts",
        "attendance_api_source_page_size",
        "attendance_api_source_lookback_days",
        "attendance_api_source_interval_minutes",
    )
    def _check_attendance_api_limits(self):
        for settings in self:
            if not 1 <= settings.attendance_api_admin_token_hours <= 720:
                raise ValidationError(_("Admin token lifetime must be between 1 and 720 hours."))
            if not 1 <= settings.attendance_api_employee_token_hours <= 720:
                raise ValidationError(_("Employee token lifetime must be between 1 and 720 hours."))
            if not 1 <= settings.attendance_api_max_page_size <= 1000:
                raise ValidationError(_("Maximum API page size must be between 1 and 1000."))
            if not 1 <= settings.attendance_api_source_timeout_seconds <= 120:
                raise ValidationError(_("Connection timeout must be between 1 and 120 seconds."))
            if not 1 <= settings.attendance_api_source_retry_attempts <= 5:
                raise ValidationError(_("Request retries must be between 1 and 5."))
            if not 1 <= settings.attendance_api_source_page_size <= 1000:
                raise ValidationError(_("External page size must be between 1 and 1000."))
            if not 1 <= settings.attendance_api_source_lookback_days <= 31:
                raise ValidationError(_("Scheduled lookback must be between 1 and 31 days."))
            if not 5 <= settings.attendance_api_source_interval_minutes <= 1440:
                raise ValidationError(
                    _("Scheduled interval must be between 5 and 1440 minutes.")
                )

    def _check_external_sync_access(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only a system administrator can configure external synchronization."))

    @api.model
    def get_values(self):
        values = super().get_values()
        values.update(
            {
                "attendance_api_source_admin_password": False,
                "attendance_api_source_admin_token": False,
            }
        )
        return values

    def set_values(self):
        password = self.attendance_api_source_admin_password
        token = self.attendance_api_source_admin_token
        result = super().set_values()
        parameters = self.env["ir.config_parameter"].sudo()
        if password:
            parameters.set_param(
                "hr_management_attend_api.source_admin_password", password
            )
        if token:
            parameters.set_param("hr_management_attend_api.source_admin_token", token)
        cron = self.env.ref(
            "hr_management_attend_api.ir_cron_pull_external_attendance",
            raise_if_not_found=False,
        )
        if cron:
            enabled = bool(self.attendance_api_source_enabled)
            cron_values = {
                "active": enabled,
                "interval_number": self.attendance_api_source_interval_minutes,
                "interval_type": "minutes",
                "numbercall": -1,
                "doall": False,
            }
            now = fields.Datetime.now()
            if enabled and (
                not cron.active
                or not cron.nextcall
                or cron.nextcall <= now
                or cron.numbercall == 0
            ):
                cron_values["nextcall"] = now + timedelta(minutes=1)
            cron.sudo().write(cron_values)
        return result

    def action_test_attendance_api_source(self):
        self.ensure_one()
        self._check_external_sync_access()
        self.execute()
        profile = self.env["hr.attendance.api.sync.service"]._test_connection()
        user = profile.get("user") if isinstance(profile.get("user"), dict) else {}
        role = profile.get("role") or user.get("role") or "admin"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connection Successful"),
                "message": _("Connected to the external HR API as %s.") % role,
                "type": "success",
                "sticky": False,
            },
        }

    def action_clear_attendance_api_source_token(self):
        self.ensure_one()
        self._check_external_sync_access()
        self.env["ir.config_parameter"].sudo().set_param(
            "hr_management_attend_api.source_admin_token", ""
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token Cleared"),
                "message": _("The next connection will request a new external token."),
                "type": "info",
                "sticky": False,
            },
        }

    def action_pull_attendance_now(self):
        self.ensure_one()
        self._check_external_sync_access()
        if not self.attendance_api_sync_date_from or not self.attendance_api_sync_date_to:
            raise ValidationError(_("Choose the pull start and end dates."))
        if (
            self.attendance_api_sync_branch_id
            and not self.attendance_api_sync_branch_id.api_external_id
        ):
            raise ValidationError(_("The selected branch has no external HR ID."))
        if (
            self.attendance_api_sync_employee_id
            and not self.attendance_api_sync_employee_id.api_employee_number
        ):
            raise ValidationError(_("The selected employee has no API Employee Number."))
        self.execute()
        log = self.env["hr.attendance.api.sync.service"]._run_sync(
            self.attendance_api_sync_date_from,
            self.attendance_api_sync_date_to,
            trigger="manual",
            branch=self.attendance_api_sync_branch_id,
            employee=self.attendance_api_sync_employee_id,
            shift=self.attendance_api_sync_shift,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendance Pull Result"),
            "res_model": "hr.attendance.api.sync.log",
            "res_id": log.id,
            "view_mode": "form",
            "target": "current",
        }
