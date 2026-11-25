import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000


class HrAttendanceApiCredential(models.Model):
    _name = "hr.attendance.api.credential"
    _description = "HR Attendance API Credential"
    _order = "login"

    employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, index=True
    )
    login = fields.Char(required=True, index=True)
    password_hash = fields.Char(required=True, groups="base.group_system")
    active = fields.Boolean(default=True)
    failed_attempts = fields.Integer(default=0, readonly=True)
    locked_until = fields.Datetime(readonly=True)
    last_login_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("employee_unique", "unique(employee_id)", "An employee can have only one API credential."),
        ("login_unique", "unique(login)", "This API login is already in use."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("login"):
                vals["login"] = vals["login"].strip().lower()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("login"):
            vals["login"] = vals["login"].strip().lower()
        return super().write(vals)

    @api.constrains("login")
    def _check_login(self):
        for credential in self:
            if not credential.login or "@" not in credential.login:
                raise ValidationError(_("The API login must be a valid email-style login."))

    @api.model
    def _hash_password(self, password):
        if not isinstance(password, str) or len(password) < 8:
            raise ValidationError(_("The API password must contain at least 8 characters."))
        if len(password) > 256:
            raise ValidationError(_("The API password cannot exceed 256 characters."))
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        )
        return "$".join(
            (
                PASSWORD_SCHEME,
                str(PASSWORD_ITERATIONS),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(digest).decode("ascii"),
            )
        )

    def _set_password(self, password):
        self.ensure_one()
        self.sudo().write(
            {
                "password_hash": self._hash_password(password),
                "failed_attempts": 0,
                "locked_until": False,
            }
        )

    def _lock_for_authentication(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM hr_attendance_api_credential WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset(["failed_attempts", "locked_until"])

    def _verify_password(self, password):
        self.ensure_one()
        try:
            scheme, iterations, salt_b64, expected_b64 = self.password_hash.split("$", 3)
            if scheme != PASSWORD_SCHEME:
                return False
            if int(iterations) != PASSWORD_ITERATIONS:
                return False
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(expected_b64.encode("ascii"))
            if len(salt) != 16 or len(expected) != 32:
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
            )
            return hmac.compare_digest(actual, expected)
        except (AttributeError, TypeError, ValueError, binascii.Error):
            return False

    def _register_failed_attempt(self):
        self.ensure_one()
        attempts = self.failed_attempts + 1
        values = {"failed_attempts": attempts}
        if attempts >= 5:
            values.update(
                {
                    "failed_attempts": 0,
                    "locked_until": fields.Datetime.now() + timedelta(minutes=15),
                }
            )
        self.sudo().write(values)

    def _register_successful_login(self):
        self.ensure_one()
        self.sudo().write(
            {
                "failed_attempts": 0,
                "locked_until": False,
                "last_login_at": fields.Datetime.now(),
            }
        )

    def _is_locked(self):
        self.ensure_one()
        return bool(self.locked_until and self.locked_until > fields.Datetime.now())
