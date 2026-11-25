import json
import logging
import math
import re
import uuid
from datetime import datetime, time, timedelta

import pytz
from psycopg2 import IntegrityError
from werkzeug.exceptions import RequestEntityTooLarge

from odoo import fields, http, _
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from ..models.attendance_service import AttendanceAPIError


_logger = logging.getLogger(__name__)


class HrManagementAttendanceAPI(http.Controller):
    def _request_id(self):
        cached = getattr(request, "_hr_attendance_api_request_id", None)
        if cached:
            return cached
        candidate = (request.httprequest.headers.get("X-Request-ID") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", candidate):
            candidate = str(uuid.uuid4())
        request._hr_attendance_api_request_id = candidate
        return candidate

    def _headers(self, request_id=None, preflight=False):
        headers = [
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Request-ID", request_id or self._request_id()),
        ]
        origin = request.httprequest.headers.get("Origin")
        allowed = request.env["ir.config_parameter"].sudo().get_param(
            "hr_management_attend_api.allowed_origins", ""
        )
        allowed_origins = {item.strip() for item in allowed.split(",") if item.strip()}
        if origin and origin in allowed_origins:
            headers.extend(
                [
                    ("Access-Control-Allow-Origin", origin),
                    ("Vary", "Origin"),
                ]
            )
            if preflight:
                headers.extend(
                    [
                        ("Access-Control-Allow-Headers", "Authorization, Content-Type, Idempotency-Key, X-Request-ID"),
                        ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
                        ("Access-Control-Max-Age", "600"),
                    ]
                )
        return headers

    def _json_response(self, payload, status=200, request_id=None):
        return request.make_json_response(
            payload, status=status, headers=self._headers(request_id=request_id)
        )

    def _error(self, message, status=400, code="bad_request", details=None, request_id=None):
        payload = {"message": message, "code": code}
        if details:
            payload["errors"] = details
        return self._json_response(payload, status=status, request_id=request_id)

    def _dispatch(self, callback):
        request_id = self._request_id()
        try:
            return self._json_response(callback(), request_id=request_id)
        except AttendanceAPIError as error:
            return self._error(
                error.message,
                status=error.status,
                code=error.code,
                details=error.details,
                request_id=request_id,
            )
        except (ValidationError, UserError) as error:
            request.env.cr.rollback()
            return self._error(
                str(error), status=422, code="validation_error", request_id=request_id
            )
        except IntegrityError:
            request.env.cr.rollback()
            return self._error(
                _("A record with the same unique value already exists."),
                status=409,
                code="unique_value_conflict",
                request_id=request_id,
            )
        except AccessDenied:
            request.env.cr.rollback()
            return self._error(
                _("Invalid login or password."),
                status=401,
                code="invalid_credentials",
                request_id=request_id,
            )
        except Exception:
            request.env.cr.rollback()
            _logger.exception("Unhandled HR attendance API error (request_id=%s)", request_id)
            return self._error(
                _("An unexpected server error occurred."),
                status=500,
                code="server_error",
                request_id=request_id,
            )

    def _body(self):
        maximum_size = 64 * 1024
        content_length = request.httprequest.content_length
        if content_length is not None and content_length > maximum_size:
            raise AttendanceAPIError(
                _("The request body is too large."),
                status=413,
                code="request_too_large",
            )
        request.httprequest.max_content_length = maximum_size
        try:
            raw = request.httprequest.get_data(as_text=True)
        except RequestEntityTooLarge:
            raise AttendanceAPIError(
                _("The request body is too large."),
                status=413,
                code="request_too_large",
            )
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            raise AttendanceAPIError(_("The request body must be valid JSON."))
        if not isinstance(payload, dict):
            raise AttendanceAPIError(_("The JSON request body must be an object."))
        return payload

    def _required(self, payload, names):
        missing = [name for name in names if payload.get(name) in (None, "")]
        if missing:
            raise AttendanceAPIError(
                _("Required fields are missing."),
                details={name: "required" for name in missing},
            )

    def _token(self, role=None):
        token = request.env["hr.attendance.api.token"]._authenticate_bearer(
            request.httprequest.headers.get("Authorization")
        )
        if not token:
            raise AttendanceAPIError(
                _("Unauthenticated."), status=401, code="unauthenticated"
            )
        if role and token.role != role:
            raise AttendanceAPIError(_("Forbidden."), status=403, code="forbidden")
        return token

    def _integer(self, value, name, default=None, minimum=None):
        if value in (None, ""):
            return default
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise AttendanceAPIError(
                _("%s must be an integer.") % name, details={name: "invalid_integer"}
            )
        if minimum is not None and result < minimum:
            raise AttendanceAPIError(
                _("%s is below the allowed minimum.") % name,
                details={name: "below_minimum"},
            )
        return result

    def _number(self, value, name):
        try:
            result = float(value)
        except (TypeError, ValueError):
            raise AttendanceAPIError(
                _("%s must be a number.") % name, details={name: "invalid_number"}
            )
        if not math.isfinite(result):
            raise AttendanceAPIError(
                _("%s must be a finite number.") % name,
                details={name: "invalid_number"},
            )
        return result

    def _string(self, value, name, maximum=256, lower=False, strip=True):
        if not isinstance(value, str):
            raise AttendanceAPIError(
                _("%s must be a string.") % name,
                details={name: "invalid_string"},
            )
        result = value.strip() if strip else value
        if not result:
            raise AttendanceAPIError(
                _("%s cannot be empty.") % name,
                details={name: "required"},
            )
        if len(result) > maximum:
            raise AttendanceAPIError(
                _("%s is too long.") % name,
                details={name: "too_long"},
            )
        return result.lower() if lower else result

    def _config_int(self, key, default, minimum=1, maximum=None):
        raw = request.env["ir.config_parameter"].sudo().get_param(key, str(default))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        value = max(minimum, value)
        return min(value, maximum) if maximum is not None else value

    def _boolean(self, value, name):
        if isinstance(value, bool):
            return value
        if value in (1, "1", "true", "True"):
            return True
        if value in (0, "0", "false", "False"):
            return False
        raise AttendanceAPIError(
            _("%s must be a boolean.") % name, details={name: "invalid_boolean"}
        )

    def _time_float(self, value, name):
        if isinstance(value, (int, float)):
            result = float(value)
        else:
            try:
                hours, minutes = str(value).split(":", 1)
                hours = int(hours)
                minutes = int(minutes)
                if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
                    raise ValueError
                result = hours + minutes / 60
            except (TypeError, ValueError):
                raise AttendanceAPIError(
                    _("%s must use HH:mm format.") % name,
                    details={name: "invalid_time"},
                )
        if result < 0 or result >= 24:
            raise AttendanceAPIError(
                _("%s must be between 00:00 and 23:59.") % name,
                details={name: "invalid_time"},
            )
        return result

    def _format_time(self, value):
        total = min(1439, max(0, int(round((value or 0.0) * 60))))
        return "%02d:%02d" % divmod(total, 60)

    def _iso_datetime(self, value):
        if not value:
            return None
        value = fields.Datetime.to_datetime(value)
        if value.tzinfo is None:
            value = pytz.utc.localize(value)
        return value.astimezone(pytz.utc).isoformat().replace("+00:00", "Z")

    def _pagination(self):
        args = request.httprequest.args
        page = self._integer(args.get("page"), "page", default=1, minimum=1)
        requested = self._integer(args.get("per_page"), "per_page", default=50, minimum=1)
        maximum = self._config_int(
            "hr_management_attend_api.max_page_size", 200, maximum=1000
        )
        return page, min(requested, maximum)

    def _page_payload(self, records, total, page, per_page, serializer):
        return {
            "data": [serializer(record) for record in records],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page if total else 0,
            },
        }

    def _serialize_branch(self, branch):
        return {
            "id": branch.id,
            "name": branch.name,
            "address": branch.address or "",
            "latitude": branch.api_latitude,
            "longitude": branch.api_longitude,
            "radius": branch.api_radius_m,
            "max_accuracy": branch.api_max_accuracy_m,
            "timezone": branch.api_timezone,
            "morning_check_in_start": self._format_time(branch.api_morning_start),
            "morning_check_in_end": self._format_time(branch.api_morning_end),
            "evening_check_in_start": self._format_time(branch.api_evening_start),
            "evening_check_in_end": self._format_time(branch.api_evening_end),
            "grace_period": branch.api_grace_period_minutes,
            "enforce_time_windows": branch.api_enforce_time_windows,
            "status": bool(branch.active and branch.api_attendance_enabled),
        }

    def _serialize_employee(self, employee):
        credential = employee.api_credential_ids[:1]
        return {
            "id": employee.id,
            "name": employee.name,
            "email": credential.login if credential else (employee.work_email or ""),
            "branch_id": employee.api_branch_id.id or None,
            "branch_name": employee.api_branch_id.name or None,
            "employee_number": employee.api_employee_number or "",
            "phone": employee.work_phone or employee.mobile_phone or "",
            "position": employee.job_title or "",
            "hire_date": fields.Date.to_string(employee.api_hire_date)
            if employee.api_hire_date
            else None,
            "status": bool(employee.active and employee.api_access_enabled),
        }

    def _serialize_attendance(self, attendance):
        return {
            "id": attendance.id,
            "employee_id": attendance.employee_id.id,
            "employee_name": attendance.employee_id.name,
            "branch_id": attendance.api_branch_id.id or None,
            "branch_name": attendance.api_branch_id.name or None,
            "check_in": self._iso_datetime(attendance.check_in),
            "check_out": self._iso_datetime(attendance.check_out),
            "check_in_period": attendance.api_check_in_period,
            "check_out_period": attendance.api_check_out_period,
            "check_in_accuracy": attendance.api_check_in_accuracy,
            "check_out_accuracy": attendance.api_check_out_accuracy,
            "check_in_distance": round(attendance.api_check_in_distance, 2),
            "check_out_distance": round(attendance.api_check_out_distance, 2),
            "source": attendance.api_source,
        }

    def _branch_values(self, payload, partial=False):
        mapping = {
            "name": "name",
            "address": "address",
            "latitude": "api_latitude",
            "longitude": "api_longitude",
            "radius": "api_radius_m",
            "max_accuracy": "api_max_accuracy_m",
            "timezone": "api_timezone",
            "grace_period": "api_grace_period_minutes",
            "enforce_time_windows": "api_enforce_time_windows",
        }
        values = {}
        for source, target in mapping.items():
            if source not in payload:
                continue
            value = payload[source]
            if source in ("latitude", "longitude", "radius", "max_accuracy"):
                value = self._number(value, source)
            elif source == "grace_period":
                value = self._integer(value, source, minimum=0)
            elif source == "enforce_time_windows":
                value = self._boolean(value, source)
            values[target] = value
        time_mapping = {
            "morning_check_in_start": "api_morning_start",
            "morning_check_in_end": "api_morning_end",
            "evening_check_in_start": "api_evening_start",
            "evening_check_in_end": "api_evening_end",
        }
        for source, target in time_mapping.items():
            if source in payload:
                values[target] = self._time_float(payload[source], source)
        if "status" in payload:
            status = self._boolean(payload["status"], "status")
            values.update({"active": status, "api_attendance_enabled": status})
        elif not partial:
            values.update({"active": True, "api_attendance_enabled": True})
        return values

    def _admin_branch(self, token, branch_id, require_available=False):
        branch = (
            request.env["res.branch"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [("id", "=", branch_id), ("company_id", "=", token.company_id.id)],
                limit=1,
            )
        )
        if not branch:
            raise AttendanceAPIError(_("Branch not found."), status=404, code="branch_not_found")
        if require_available and (not branch.active or not branch.api_attendance_enabled):
            raise AttendanceAPIError(
                _("The attendance branch is not active."),
                status=422,
                code="branch_not_available",
            )
        return branch

    def _admin_employee(self, token, employee_id):
        employee = request.env["hr.employee"].sudo().with_context(active_test=False).search(
            [("id", "=", employee_id), ("company_id", "=", token.company_id.id)],
            limit=1,
        )
        if not employee:
            raise AttendanceAPIError(
                _("Employee not found."), status=404, code="employee_not_found"
            )
        return employee

    def _ensure_branch_has_no_open_attendance(self, branch):
        open_attendance = request.env["hr.attendance"].sudo().search_count(
            [("api_branch_id", "=", branch.id), ("check_out", "=", False)]
        )
        if open_attendance:
            raise AttendanceAPIError(
                _("The branch cannot be deactivated while employees are checked in."),
                status=409,
                code="open_attendance_exists",
            )

    def _ensure_employee_has_no_open_attendance(self, employee):
        open_attendance = request.env["hr.attendance"].sudo().search_count(
            [("employee_id", "=", employee.id), ("check_out", "=", False)]
        )
        if open_attendance:
            raise AttendanceAPIError(
                _("The employee cannot be deactivated while checked in."),
                status=409,
                code="open_attendance_exists",
            )

    def _revoke_employee_tokens(self, employee):
        tokens = request.env["hr.attendance.api.token"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("revoked_at", "=", False),
            ]
        )
        if tokens:
            tokens.write({"revoked_at": fields.Datetime.now()})

    def _revoke_branch_employee_tokens(self, branch):
        tokens = request.env["hr.attendance.api.token"].sudo().search(
            [
                ("employee_id.api_branch_id", "=", branch.id),
                ("revoked_at", "=", False),
            ]
        )
        if tokens:
            tokens.write({"revoked_at": fields.Datetime.now()})

    @http.route(
        ["/api", "/api/<path:subpath>"],
        type="http",
        auth="public",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def api_options(self, subpath=None, **kwargs):
        return request.make_response("", status=204, headers=self._headers(preflight=True))

    @http.route(
        "/api/login",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def login(self, **kwargs):
        def execute():
            payload = self._body()
            self._required(payload, ("email", "password"))
            submitted_login = self._string(payload["email"], "email", maximum=254)
            employee_login = submitted_login.lower()
            password = self._string(
                payload["password"], "password", maximum=256, strip=False
            )
            credential = request.env["hr.attendance.api.credential"].sudo().search(
                [("login", "=", employee_login), ("active", "=", True)], limit=1
            )
            if credential:
                credential._lock_for_authentication()
                if credential._is_locked():
                    raise AttendanceAPIError(
                        _("Too many failed login attempts. Try again later."),
                        status=429,
                        code="login_temporarily_locked",
                    )
                if not credential._verify_password(password):
                    credential._register_failed_attempt()
                    raise AttendanceAPIError(
                        _("Invalid login or password."),
                        status=401,
                        code="invalid_credentials",
                    )
                employee = credential.employee_id
                if not employee.active or not employee.api_access_enabled:
                    raise AttendanceAPIError(
                        _("Employee API access is disabled."),
                        status=403,
                        code="employee_api_disabled",
                    )
                if (
                    not employee.api_branch_id
                    or not employee.api_branch_id.active
                    or not employee.api_branch_id.api_attendance_enabled
                ):
                    raise AttendanceAPIError(
                        _("The employee's attendance branch is not available."),
                        status=403,
                        code="branch_not_available",
                    )
                credential._register_successful_login()
                hours = self._config_int(
                    "hr_management_attend_api.employee_token_hours", 24, maximum=720
                )
                token, raw_token = request.env["hr.attendance.api.token"]._issue(
                    "employee",
                    employee.company_id,
                    employee=employee,
                    lifetime_hours=hours,
                )
                return {
                    "token": raw_token,
                    "token_type": "Bearer",
                    "role": "employee",
                    "expires_at": self._iso_datetime(token.expires_at),
                    "user": self._serialize_employee(employee),
                }

            user_agent_env = {
                "interactive": False,
                "HTTP_HOST": request.httprequest.environ.get("HTTP_HOST", ""),
                "REMOTE_ADDR": request.httprequest.remote_addr or "",
            }
            uid = request.env["res.users"].authenticate(
                request.db, submitted_login, password, user_agent_env
            )
            user = request.env["res.users"].sudo().browse(uid)
            if not user.exists() or not (
                user.has_group("hr_management_attend_api.group_attendance_api_admin")
                or user.has_group("base.group_system")
            ):
                raise AttendanceAPIError(_("Forbidden."), status=403, code="forbidden")
            hours = self._config_int(
                "hr_management_attend_api.admin_token_hours", 12, maximum=720
            )
            token, raw_token = request.env["hr.attendance.api.token"]._issue(
                "admin", user.company_id, user=user, lifetime_hours=hours
            )
            return {
                "token": raw_token,
                "token_type": "Bearer",
                "role": "admin",
                "expires_at": self._iso_datetime(token.expires_at),
                "user": {"id": user.id, "name": user.name, "email": user.login},
            }

        return self._dispatch(execute)

    @http.route(
        "/api/me",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def me(self, **kwargs):
        def execute():
            token = self._token()
            if token.role == "employee":
                return {"role": "employee", "user": self._serialize_employee(token.employee_id)}
            return {
                "role": "admin",
                "user": {
                    "id": token.user_id.id,
                    "name": token.user_id.name,
                    "email": token.user_id.login,
                    "company_id": token.company_id.id,
                },
            }

        return self._dispatch(execute)

    @http.route(
        "/api/logout",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def logout(self, **kwargs):
        def execute():
            self._token()._revoke()
            return {"message": _("Logged out successfully.")}

        return self._dispatch(execute)

    @http.route(
        "/api/attendance/check-in",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def attendance_check_in(self, **kwargs):
        def execute():
            token = self._token("employee")
            payload = self._body()
            self._required(payload, ("latitude", "longitude", "accuracy", "shift"))
            attendance, replayed = request.env["hr.attendance.api.service"]._check_in(
                token.employee_id,
                payload,
                token=token,
                idempotency_key=request.httprequest.headers.get("Idempotency-Key"),
                source_ip=request.httprequest.remote_addr,
                request_id=self._request_id(),
            )
            return {
                "message": _("Check-in recorded successfully."),
                "replayed": replayed,
                "data": self._serialize_attendance(attendance),
            }

        return self._dispatch(execute)

    @http.route(
        "/api/attendance/check-out",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def attendance_check_out(self, **kwargs):
        def execute():
            token = self._token("employee")
            payload = self._body()
            self._required(payload, ("latitude", "longitude", "accuracy", "shift"))
            attendance, replayed = request.env["hr.attendance.api.service"]._check_out(
                token.employee_id,
                payload,
                token=token,
                idempotency_key=request.httprequest.headers.get("Idempotency-Key"),
                source_ip=request.httprequest.remote_addr,
                request_id=self._request_id(),
            )
            return {
                "message": _("Check-out recorded successfully."),
                "replayed": replayed,
                "data": self._serialize_attendance(attendance),
            }

        return self._dispatch(execute)

    @http.route(
        "/api/admin/branches",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def admin_branches(self, **kwargs):
        def execute():
            token = self._token("admin")
            page, per_page = self._pagination()
            domain = [("company_id", "=", token.company_id.id)]
            model = request.env["res.branch"].sudo().with_context(active_test=False)
            total = model.search_count(domain)
            records = model.search(
                domain, order="name, id", offset=(page - 1) * per_page, limit=per_page
            )
            return self._page_payload(records, total, page, per_page, self._serialize_branch)

        return self._dispatch(execute)

    @http.route(
        "/api/admin/branches",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def admin_branch_create(self, **kwargs):
        def execute():
            token = self._token("admin")
            payload = self._body()
            self._required(
                payload,
                (
                    "name",
                    "latitude",
                    "longitude",
                    "radius",
                    "morning_check_in_start",
                    "morning_check_in_end",
                    "evening_check_in_start",
                    "evening_check_in_end",
                ),
            )
            values = self._branch_values(payload)
            values["company_id"] = token.company_id.id
            branch = request.env["res.branch"].sudo().create(values)
            return {"message": _("Branch created successfully."), "data": self._serialize_branch(branch)}

        return self._dispatch(execute)

    @http.route(
        "/api/admin/branches/<int:branch_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def admin_branch_get(self, branch_id, **kwargs):
        return self._dispatch(
            lambda: {"data": self._serialize_branch(self._admin_branch(self._token("admin"), branch_id))}
        )

    @http.route(
        "/api/admin/branches/<int:branch_id>",
        type="http",
        auth="public",
        methods=["PUT"],
        csrf=False,
        save_session=False,
    )
    def admin_branch_update(self, branch_id, **kwargs):
        def execute():
            token = self._token("admin")
            branch = self._admin_branch(token, branch_id)
            values = self._branch_values(self._body(), partial=True)
            attendance_sensitive = {
                "active",
                "api_attendance_enabled",
                "api_latitude",
                "api_longitude",
                "api_radius_m",
                "api_max_accuracy_m",
                "api_timezone",
            }
            sensitive_changes = {
                field_name
                for field_name in attendance_sensitive.intersection(values)
                if branch[field_name] != values[field_name]
            }
            if sensitive_changes:
                self._ensure_branch_has_no_open_attendance(branch)
            if values.get("active") is False or values.get("api_attendance_enabled") is False:
                self._revoke_branch_employee_tokens(branch)
            branch.sudo().write(values)
            return {"message": _("Branch updated successfully."), "data": self._serialize_branch(branch)}

        return self._dispatch(execute)

    @http.route(
        "/api/admin/branches/<int:branch_id>",
        type="http",
        auth="public",
        methods=["DELETE"],
        csrf=False,
        save_session=False,
    )
    def admin_branch_delete(self, branch_id, **kwargs):
        def execute():
            token = self._token("admin")
            branch = self._admin_branch(token, branch_id)
            self._ensure_branch_has_no_open_attendance(branch)
            self._revoke_branch_employee_tokens(branch)
            branch.sudo().write({"active": False, "api_attendance_enabled": False})
            return {"message": _("Branch deactivated successfully.")}

        return self._dispatch(execute)

    @http.route(
        "/api/admin/employees",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def admin_employees(self, **kwargs):
        def execute():
            token = self._token("admin")
            page, per_page = self._pagination()
            domain = [
                ("company_id", "=", token.company_id.id),
                ("api_branch_id", "!=", False),
            ]
            model = request.env["hr.employee"].sudo().with_context(active_test=False)
            total = model.search_count(domain)
            records = model.search(
                domain, order="name, id", offset=(page - 1) * per_page, limit=per_page
            )
            return self._page_payload(records, total, page, per_page, self._serialize_employee)

        return self._dispatch(execute)

    @http.route(
        "/api/admin/employees",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def admin_employee_create(self, **kwargs):
        def execute():
            token = self._token("admin")
            payload = self._body()
            self._required(
                payload,
                ("name", "email", "password", "branch_id", "employee_number"),
            )
            branch = self._admin_branch(
                token,
                self._integer(payload["branch_id"], "branch_id", minimum=1),
                require_available=True,
            )
            hire_date = False
            if payload.get("hire_date"):
                try:
                    hire_date = fields.Date.to_date(payload["hire_date"])
                except (TypeError, ValueError):
                    raise AttendanceAPIError(
                        _("hire_date must use YYYY-MM-DD format."),
                        details={"hire_date": "invalid_date"},
                    )
            employee_name = self._string(payload["name"], "name", maximum=256)
            email = self._string(payload["email"], "email", maximum=254, lower=True)
            employee_number = self._string(
                payload["employee_number"], "employee_number", maximum=128
            )
            password = self._string(
                payload["password"], "password", maximum=256, strip=False
            )
            employee = request.env["hr.employee"].sudo().create(
                {
                    "name": employee_name,
                    "company_id": token.company_id.id,
                    "work_email": email,
                    "work_phone": payload.get("phone"),
                    "job_title": payload.get("position"),
                    "api_branch_id": branch.id,
                    "api_employee_number": employee_number,
                    "api_hire_date": hire_date,
                    "api_access_enabled": True,
                }
            )
            credential_model = request.env["hr.attendance.api.credential"].sudo()
            credential_model.create(
                {
                    "employee_id": employee.id,
                    "login": email,
                    "password_hash": credential_model._hash_password(password),
                }
            )
            return {
                "message": _("Employee created successfully."),
                "data": self._serialize_employee(employee),
            }

        return self._dispatch(execute)

    @http.route(
        "/api/admin/employees/<int:employee_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def admin_employee_get(self, employee_id, **kwargs):
        return self._dispatch(
            lambda: {
                "data": self._serialize_employee(
                    self._admin_employee(self._token("admin"), employee_id)
                )
            }
        )

    @http.route(
        "/api/admin/employees/<int:employee_id>",
        type="http",
        auth="public",
        methods=["PUT"],
        csrf=False,
        save_session=False,
    )
    def admin_employee_update(self, employee_id, **kwargs):
        def execute():
            token = self._token("admin")
            employee = self._admin_employee(token, employee_id)
            payload = self._body()
            values = {}
            requested_status = None
            for source, target in (
                ("name", "name"),
                ("phone", "work_phone"),
                ("position", "job_title"),
                ("employee_number", "api_employee_number"),
            ):
                if source in payload:
                    values[target] = payload[source]
            if "branch_id" in payload:
                target_branch = self._admin_branch(
                    token,
                    self._integer(payload["branch_id"], "branch_id", minimum=1),
                    require_available=True,
                )
                if target_branch != employee.api_branch_id:
                    self._ensure_employee_has_no_open_attendance(employee)
                values["api_branch_id"] = target_branch.id
            if "hire_date" in payload:
                try:
                    values["api_hire_date"] = fields.Date.to_date(payload["hire_date"])
                except (TypeError, ValueError):
                    raise AttendanceAPIError(
                        _("hire_date must use YYYY-MM-DD format."),
                        details={"hire_date": "invalid_date"},
                    )
            if "status" in payload:
                status = self._boolean(payload["status"], "status")
                if not status:
                    self._ensure_employee_has_no_open_attendance(employee)
                elif not values.get("api_branch_id") and (
                    not employee.api_branch_id
                    or not employee.api_branch_id.active
                    or not employee.api_branch_id.api_attendance_enabled
                ):
                    raise AttendanceAPIError(
                        _("The employee cannot be activated without an active attendance branch."),
                        status=422,
                        code="branch_not_available",
                    )
                values.update({"active": status, "api_access_enabled": status})
                requested_status = status
            credential = employee.with_context(active_test=False).api_credential_ids[:1].sudo()
            login = employee.work_email or ""
            if "email" in payload:
                login = self._string(
                    payload["email"], "email", maximum=254, lower=True
                )
                values["work_email"] = login
            if not credential and ("email" in payload or "password" in payload):
                self._required(
                    {"email": login, "password": payload.get("password")},
                    ("email", "password"),
                )
                credential_model = request.env["hr.attendance.api.credential"].sudo()
                password = self._string(
                    payload["password"], "password", maximum=256, strip=False
                )
                credential = credential_model.create(
                    {
                        "employee_id": employee.id,
                        "login": login,
                        "password_hash": credential_model._hash_password(password),
                    }
                )
            else:
                if credential and "email" in payload:
                    credential.write({"login": login})
                if credential and "password" in payload:
                    credential._set_password(
                        self._string(
                            payload["password"], "password", maximum=256, strip=False
                        )
                    )
            if credential and requested_status is not None:
                credential.write({"active": requested_status})
            if requested_status is False or "password" in payload:
                self._revoke_employee_tokens(employee)
            employee.sudo().write(values)
            return {
                "message": _("Employee updated successfully."),
                "data": self._serialize_employee(employee),
            }

        return self._dispatch(execute)

    @http.route(
        "/api/admin/employees/<int:employee_id>",
        type="http",
        auth="public",
        methods=["DELETE"],
        csrf=False,
        save_session=False,
    )
    def admin_employee_delete(self, employee_id, **kwargs):
        def execute():
            token = self._token("admin")
            employee = self._admin_employee(token, employee_id)
            self._ensure_employee_has_no_open_attendance(employee)
            self._revoke_employee_tokens(employee)
            employee.api_credential_ids.sudo().write({"active": False})
            employee.sudo().write({"active": False, "api_access_enabled": False})
            return {"message": _("Employee deactivated successfully.")}

        return self._dispatch(execute)

    def _attendance_domain(self, token):
        args = request.httprequest.args
        domain = [("employee_id.company_id", "=", token.company_id.id)]
        branch = False
        if args.get("branch_id"):
            branch = self._admin_branch(
                token, self._integer(args.get("branch_id"), "branch_id", minimum=1)
            )
            domain.append(("api_branch_id", "=", branch.id))
        if args.get("employee_id"):
            employee = self._admin_employee(
                token, self._integer(args.get("employee_id"), "employee_id", minimum=1)
            )
            domain.append(("employee_id", "=", employee.id))
        if args.get("shift"):
            shift = args.get("shift")
            if shift not in ("morning", "evening"):
                raise AttendanceAPIError(
                    _("shift must be either 'morning' or 'evening'."),
                    details={"shift": "invalid_choice"},
                )
            domain.extend(
                [
                    "|",
                    ("api_check_in_period", "=", shift),
                    ("api_check_out_period", "=", shift),
                ]
            )
        if args.get("date"):
            try:
                local_date = fields.Date.to_date(args.get("date"))
            except (TypeError, ValueError):
                raise AttendanceAPIError(
                    _("date must use YYYY-MM-DD format."),
                    details={"date": "invalid_date"},
                )
            timezone = pytz.timezone(
                (branch and branch.api_timezone)
                or token.company_id.partner_id.tz
                or "UTC"
            )
            start = timezone.localize(datetime.combine(local_date, time.min))
            end = start + timedelta(days=1)
            domain.extend(
                [
                    ("check_in", ">=", start.astimezone(pytz.utc).replace(tzinfo=None)),
                    ("check_in", "<", end.astimezone(pytz.utc).replace(tzinfo=None)),
                ]
            )
        return domain

    @http.route(
        "/api/admin/attendances",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def admin_attendances(self, **kwargs):
        def execute():
            token = self._token("admin")
            page, per_page = self._pagination()
            model = request.env["hr.attendance"].sudo()
            domain = self._attendance_domain(token)
            total = model.search_count(domain)
            records = model.search(
                domain,
                order="check_in desc, id desc",
                offset=(page - 1) * per_page,
                limit=per_page,
            )
            return self._page_payload(records, total, page, per_page, self._serialize_attendance)

        return self._dispatch(execute)

    @http.route(
        "/api/admin/attendances/<int:attendance_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def admin_attendance_get(self, attendance_id, **kwargs):
        def execute():
            token = self._token("admin")
            attendance = request.env["hr.attendance"].sudo().search(
                [
                    ("id", "=", attendance_id),
                    ("employee_id.company_id", "=", token.company_id.id),
                ],
                limit=1,
            )
            if not attendance:
                raise AttendanceAPIError(
                    _("Attendance record not found."),
                    status=404,
                    code="attendance_not_found",
                )
            data = self._serialize_attendance(attendance)
            data["events"] = [
                {
                    "request_id": event.request_id,
                    "event_type": event.event_type,
                    "period": event.period,
                    "event_at": self._iso_datetime(event.event_at),
                    "latitude": event.latitude,
                    "longitude": event.longitude,
                    "accuracy": event.accuracy,
                    "distance": round(event.distance, 2),
                }
                for event in attendance.api_event_ids.sorted("event_at")
            ]
            return {"data": data}

        return self._dispatch(execute)
