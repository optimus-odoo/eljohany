import math
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _


class AttendanceAPIError(Exception):
    def __init__(self, message, status=400, code="validation_error", details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details or {}


class HrAttendanceApiService(models.AbstractModel):
    _name = "hr.attendance.api.service"
    _description = "HR Attendance API Service"

    @api.model
    def _number(self, value, field_name):
        try:
            result = float(value)
        except (TypeError, ValueError):
            raise AttendanceAPIError(
                _("%s must be a number.") % field_name,
                details={field_name: "invalid_number"},
            )
        if not math.isfinite(result):
            raise AttendanceAPIError(
                _("%s must be a finite number.") % field_name,
                details={field_name: "invalid_number"},
            )
        return result

    @api.model
    def _validate_period(self, period):
        if period not in ("morning", "evening"):
            raise AttendanceAPIError(
                _("shift must be either 'morning' or 'evening'."),
                details={"shift": "invalid_choice"},
            )
        return period

    @api.model
    def _distance_m(self, latitude, longitude, branch):
        radius_km = 6371.0088
        lat1 = math.radians(latitude)
        lon1 = math.radians(longitude)
        lat2 = math.radians(branch.api_latitude)
        lon2 = math.radians(branch.api_longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        value = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return radius_km * 2000 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    @api.model
    def _validate_geo(self, payload, branch):
        latitude = self._number(payload.get("latitude"), "latitude")
        longitude = self._number(payload.get("longitude"), "longitude")
        accuracy = self._number(payload.get("accuracy"), "accuracy")
        if not -90 <= latitude <= 90:
            raise AttendanceAPIError(
                _("latitude must be between -90 and 90."),
                details={"latitude": "out_of_range"},
            )
        if not -180 <= longitude <= 180:
            raise AttendanceAPIError(
                _("longitude must be between -180 and 180."),
                details={"longitude": "out_of_range"},
            )
        if accuracy < 0 or accuracy > branch.api_max_accuracy_m:
            raise AttendanceAPIError(
                _("GPS accuracy is outside the allowed limit."),
                status=422,
                code="gps_accuracy_rejected",
                details={"maximum_accuracy": branch.api_max_accuracy_m},
            )
        distance = self._distance_m(latitude, longitude, branch)
        if distance > branch.api_radius_m:
            raise AttendanceAPIError(
                _("The employee is outside the allowed branch radius."),
                status=422,
                code="outside_branch_radius",
                details={
                    "distance": round(distance, 2),
                    "allowed_radius": branch.api_radius_m,
                },
            )
        return latitude, longitude, accuracy, distance

    @api.model
    def _local_datetime(self, branch, value=None):
        value = fields.Datetime.to_datetime(value or fields.Datetime.now())
        value = pytz.utc.localize(value) if value.tzinfo is None else value.astimezone(pytz.utc)
        return value.astimezone(pytz.timezone(branch.api_timezone or "UTC"))

    @api.model
    def _validate_check_in_window(self, branch, period, event_at):
        if not branch.api_enforce_time_windows:
            return
        if period == "morning":
            start = branch.api_morning_start * 60
            end = branch.api_morning_end * 60
        else:
            start = branch.api_evening_start * 60
            end = branch.api_evening_end * 60
        end += branch.api_grace_period_minutes
        current = event_at.hour * 60 + event_at.minute + event_at.second / 60
        if end < start:
            end += 1440
            if current < start:
                current += 1440
        elif end >= 1440 and current < start:
            current += 1440
        if not start <= current <= end:
            raise AttendanceAPIError(
                _("Check-in is outside the configured attendance window."),
                status=422,
                code="outside_attendance_window",
            )

    @api.model
    def _validate_employee(self, employee, require_active_branch=True):
        if not employee or not employee.exists() or not employee.active:
            raise AttendanceAPIError(_("Employee not found."), status=404, code="employee_not_found")
        if not employee.api_access_enabled:
            raise AttendanceAPIError(
                _("Attendance API access is disabled for this employee."),
                status=403,
                code="employee_api_disabled",
            )
        branch = employee.api_branch_id
        if not branch or (
            require_active_branch
            and (not branch.active or not branch.api_attendance_enabled)
        ):
            raise AttendanceAPIError(
                _("The employee's attendance branch is not available."),
                status=422,
                code="branch_not_available",
            )
        if branch.company_id != employee.company_id:
            raise AttendanceAPIError(
                _("Employee and branch companies do not match."),
                status=422,
                code="company_mismatch",
            )
        return branch

    @api.model
    def _lock_employee(self, employee):
        self.env.cr.execute(
            "SELECT id FROM hr_employee WHERE id = %s FOR UPDATE", [employee.id]
        )

    @api.model
    def _utc_day_bounds(self, branch, local_date):
        timezone = pytz.timezone(branch.api_timezone or "UTC")
        start = timezone.localize(datetime.combine(local_date, time.min))
        end = start + timedelta(days=1)
        return (
            start.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def _find_replay(self, employee, idempotency_key):
        if not idempotency_key:
            return self.env["hr.attendance.api.event"]
        if len(idempotency_key) > 128:
            raise AttendanceAPIError(
                _("Idempotency-Key cannot exceed 128 characters."),
                details={"idempotency_key": "too_long"},
            )
        return self.env["hr.attendance.api.event"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("idempotency_key", "=", idempotency_key),
            ],
            limit=1,
        )

    @api.model
    def _event_values(
        self,
        event_type,
        period,
        employee,
        attendance,
        branch,
        token,
        event_at,
        geo,
        idempotency_key,
        source_ip,
        request_id,
    ):
        latitude, longitude, accuracy, distance = geo
        values = {
            "idempotency_key": idempotency_key or False,
            "event_type": event_type,
            "period": period,
            "event_at": event_at,
            "employee_id": employee.id,
            "attendance_id": attendance.id,
            "branch_id": branch.id,
            "token_id": token.id if token else False,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "distance": distance,
            "source_ip": source_ip or False,
        }
        if request_id:
            values["request_id"] = request_id
        return values

    @api.model
    def _check_in(
        self,
        employee,
        payload,
        token=None,
        idempotency_key=None,
        source_ip=None,
        request_id=None,
    ):
        employee = employee.sudo()
        branch = self._validate_employee(employee)
        period = self._validate_period(payload.get("shift"))
        event_at = fields.Datetime.now()
        local_event_at = self._local_datetime(branch, event_at)
        self._validate_check_in_window(branch, period, local_event_at)
        geo = self._validate_geo(payload, branch)
        self._lock_employee(employee)

        replay = self._find_replay(employee, idempotency_key)
        if replay:
            if replay.event_type != "check_in":
                raise AttendanceAPIError(
                    _("The idempotency key was already used for another operation."),
                    status=409,
                    code="idempotency_conflict",
                )
            return replay.attendance_id, True

        attendance_model = self.env["hr.attendance"].sudo()
        open_attendance = attendance_model.search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)],
            limit=1,
        )
        if open_attendance:
            raise AttendanceAPIError(
                _("The employee is already checked in."),
                status=409,
                code="already_checked_in",
            )

        day_start, day_end = self._utc_day_bounds(branch, local_event_at.date())
        completed_today = attendance_model.search_count(
            [
                ("employee_id", "=", employee.id),
                ("check_in", ">=", day_start),
                ("check_in", "<", day_end),
                ("check_out", "!=", False),
            ]
        )
        if completed_today:
            raise AttendanceAPIError(
                _("Attendance has already been completed for this employee today."),
                status=409,
                code="daily_attendance_completed",
            )

        latitude, longitude, accuracy, distance = geo
        values = {
            "employee_id": employee.id,
            "check_in": event_at,
            "api_branch_id": branch.id,
            "api_check_in_period": period,
            "api_check_in_accuracy": accuracy,
            "api_check_in_distance": distance,
            "api_source": "mobile_api",
        }
        if "in_latitude" in attendance_model._fields:
            values.update({"in_latitude": latitude, "in_longitude": longitude})
        attendance = attendance_model.create(values)
        self.env["hr.attendance.api.event"].sudo().create(
            self._event_values(
                "check_in",
                period,
                employee,
                attendance,
                branch,
                token,
                event_at,
                geo,
                idempotency_key,
                source_ip,
                request_id,
            )
        )
        return attendance, False

    @api.model
    def _check_out(
        self,
        employee,
        payload,
        token=None,
        idempotency_key=None,
        source_ip=None,
        request_id=None,
    ):
        employee = employee.sudo()
        self._validate_employee(employee, require_active_branch=False)
        period = self._validate_period(payload.get("shift"))
        self._lock_employee(employee)

        replay = self._find_replay(employee, idempotency_key)
        if replay:
            if replay.event_type != "check_out":
                raise AttendanceAPIError(
                    _("The idempotency key was already used for another operation."),
                    status=409,
                    code="idempotency_conflict",
                )
            return replay.attendance_id, True

        attendance = self.env["hr.attendance"].sudo().search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)],
            order="check_in desc",
            limit=1,
        )
        if not attendance:
            raise AttendanceAPIError(
                _("The employee is not checked in."),
                status=409,
                code="not_checked_in",
            )
        branch = attendance.api_branch_id or employee.api_branch_id
        geo = self._validate_geo(payload, branch)
        event_at = fields.Datetime.now()
        if event_at <= attendance.check_in:
            raise AttendanceAPIError(
                _("Check-out must be later than check-in."),
                status=409,
                code="invalid_attendance_order",
            )
        latitude, longitude, accuracy, distance = geo
        values = {
            "check_out": event_at,
            "api_check_out_period": period,
            "api_check_out_accuracy": accuracy,
            "api_check_out_distance": distance,
        }
        attendance_model = self.env["hr.attendance"]
        if "out_latitude" in attendance_model._fields:
            values.update({"out_latitude": latitude, "out_longitude": longitude})
        attendance.sudo().write(values)
        self.env["hr.attendance.api.event"].sudo().create(
            self._event_values(
                "check_out",
                period,
                employee,
                attendance,
                branch,
                token,
                event_at,
                geo,
                idempotency_key,
                source_ip,
                request_id,
            )
        )
        return attendance, False
