import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrAttendanceApiToken(models.Model):
    _name = "hr.attendance.api.token"
    _description = "HR Attendance API Token"
    _order = "create_date desc"

    name = fields.Char(required=True, default="API Token")
    token_digest = fields.Char(required=True, index=True, groups="base.group_system")
    role = fields.Selection(
        [("admin", "Administrator"), ("employee", "Employee")],
        required=True,
        index=True,
    )
    user_id = fields.Many2one("res.users", ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    expires_at = fields.Datetime(required=True, index=True)
    revoked_at = fields.Datetime(index=True)
    last_used_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("token_digest_unique", "unique(token_digest)", "The API token digest must be unique."),
    ]

    @api.constrains("role", "user_id", "employee_id", "company_id")
    def _check_token_owner(self):
        for token in self:
            if token.role == "admin":
                if not token.user_id or token.employee_id:
                    raise ValidationError(_("An administrator token must belong only to an Odoo user."))
                if token.company_id not in token.user_id.company_ids:
                    raise ValidationError(_("The token company is not available to this administrator."))
            elif token.role == "employee":
                if not token.employee_id or token.user_id:
                    raise ValidationError(_("An employee token must belong only to an employee."))
                if token.company_id != token.employee_id.company_id:
                    raise ValidationError(_("The employee token company does not match the employee."))

    @api.model
    def _digest(self, raw_token):
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @api.model
    def _issue(self, role, company, user=None, employee=None, lifetime_hours=12):
        raw_token = "hmaa_" + secrets.token_urlsafe(48)
        token = self.sudo().create(
            {
                "name": "%s API Token" % (employee.name if employee else user.name),
                "token_digest": self._digest(raw_token),
                "role": role,
                "user_id": user.id if user else False,
                "employee_id": employee.id if employee else False,
                "company_id": company.id,
                "expires_at": fields.Datetime.now()
                + timedelta(hours=max(1, int(lifetime_hours))),
            }
        )
        return token, raw_token

    @api.model
    def _authenticate_bearer(self, authorization):
        if not authorization or not authorization.lower().startswith("bearer "):
            return self.browse()
        raw_token = authorization.split(None, 1)[1].strip()
        if not raw_token or len(raw_token) > 512:
            return self.browse()
        token = self.sudo().search(
            [
                ("token_digest", "=", self._digest(raw_token)),
                ("revoked_at", "=", False),
                ("expires_at", ">", fields.Datetime.now()),
            ],
            limit=1,
        )
        if not token:
            return token
        if token.role == "employee":
            employee = token.employee_id
            if (
                not employee
                or not employee.active
                or not employee.api_access_enabled
                or not employee.api_branch_id
                or not employee.api_branch_id.active
                or not employee.api_branch_id.api_attendance_enabled
                or token.company_id != employee.company_id
            ):
                return self.browse()
        else:
            user = token.user_id
            if (
                not user
                or not user.active
                or token.company_id not in user.company_ids
                or not (
                    user.has_group("hr_management_attend_api.group_attendance_api_admin")
                    or user.has_group("base.group_system")
                )
            ):
                return self.browse()
        now = fields.Datetime.now()
        if not token.last_used_at or token.last_used_at < now - timedelta(minutes=5):
            token.sudo().write({"last_used_at": now})
        return token

    def _revoke(self):
        self.sudo().write({"revoked_at": fields.Datetime.now()})

    @api.model
    def _cron_cleanup_tokens(self):
        cutoff = fields.Datetime.now() - timedelta(days=30)
        stale = self.sudo().search(
            [
                "|",
                ("expires_at", "<", cutoff),
                "&",
                ("revoked_at", "!=", False),
                ("revoked_at", "<", cutoff),
            ]
        )
        stale.unlink()
