import hashlib
import logging
import math
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import pytz
import requests as http_requests
from dateutil import parser as dateutil_parser

from odoo import api, fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


_TIME_ONLY_PATTERN = re.compile(
    r"^\s*\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:[AaPp][Mm])?\s*$"
)
_SYNC_ADVISORY_LOCK_KEY = 1213358420
_TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


class HrAttendanceApiSyncService(models.AbstractModel):
    _name = "hr.attendance.api.sync.service"
    _description = "HR Attendance External Sync Service"

    @api.model
    def _parameter(self, name, default=""):
        return self.env["ir.config_parameter"].sudo().get_param(
            "hr_management_attend_api.%s" % name, default
        )

    @api.model
    def _boolean_parameter(self, name, default=False):
        value = self._parameter(name, "True" if default else "False")
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @api.model
    def _integer_parameter(self, name, default, minimum=1, maximum=None):
        try:
            value = int(self._parameter(name, str(default)))
        except (TypeError, ValueError):
            value = default
        value = max(minimum, value)
        return min(value, maximum) if maximum is not None else value

    @api.model
    def _config(self):
        company_id = self._integer_parameter(
            "source_company_id", self.env.company.id, minimum=1
        )
        company = self.env["res.company"].sudo().browse(company_id).exists()
        if not company:
            company = self.env.company
        return {
            "base_url": self._parameter(
                "source_base_url", "https://hr2.sitksa-eg.com/api"
            ).strip().rstrip("/"),
            "email": self._parameter("source_admin_email", "").strip(),
            "password": self._parameter("source_admin_password", ""),
            "token": self._parameter("source_admin_token", "").strip(),
            "verify_ssl": self._boolean_parameter("source_verify_ssl", True),
            "timeout": self._integer_parameter(
                "source_timeout_seconds", 20, maximum=120
            ),
            "retry_attempts": self._integer_parameter(
                "source_retry_attempts", 3, maximum=5
            ),
            "page_size": self._integer_parameter(
                "source_page_size", 200, maximum=1000
            ),
            "timezone": self._parameter("source_timezone", "Asia/Riyadh")
            or "Asia/Riyadh",
            "sync_branches": self._boolean_parameter("source_sync_branches", True),
            "sync_employees": self._boolean_parameter("source_sync_employees", True),
            "create_branches": self._boolean_parameter(
                "source_create_missing_branches", False
            ),
            "create_employees": self._boolean_parameter(
                "source_create_missing_employees", False
            ),
            "update_references": self._boolean_parameter(
                "source_update_reference_data", False
            ),
            "company": company,
        }

    @api.model
    def _send_request(self, method, url, config, **kwargs):
        """Send an upstream request with bounded transient-error retries."""
        attempts = max(1, min(int(config.get("retry_attempts", 3)), 5))
        last_error = False
        for attempt in range(1, attempts + 1):
            try:
                response = http_requests.request(method, url, **kwargs)
            except http_requests.RequestException as error:
                last_error = error
                if attempt >= attempts:
                    break
            else:
                if (
                    response.status_code not in _TRANSIENT_HTTP_STATUSES
                    or attempt >= attempts
                ):
                    return response
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(0.0, min(float(retry_after), 10.0))
                except (TypeError, ValueError):
                    delay = min(2 ** (attempt - 1), 5)
                time.sleep(delay)
                continue
            time.sleep(min(2 ** (attempt - 1), 5))
        raise UserError(_("Could not connect to the external HR API: %s") % last_error)

    @api.model
    def _validated_base_url(self, base_url):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise UserError(_("The external HR API URL is invalid."))
        return base_url.rstrip("/")

    @api.model
    def _decode_response(self, response):
        if len(response.content) > 10 * 1024 * 1024:
            raise UserError(_("The external HR API response is too large."))
        try:
            return response.json()
        except ValueError:
            raise UserError(_("The external HR API returned invalid JSON."))

    @api.model
    def _login(self, config):
        if not config["email"] or not config["password"]:
            raise UserError(
                _("Configure an external administrator email and password or token.")
            )
        url = "%s/login" % self._validated_base_url(config["base_url"])
        try:
            response = self._send_request(
                "POST",
                url,
                config,
                json={"email": config["email"], "password": config["password"]},
                headers={"Accept": "application/json"},
                timeout=config["timeout"],
                verify=config["verify_ssl"],
                allow_redirects=False,
            )
        except http_requests.RequestException as error:
            raise UserError(_("Could not connect to the external HR API: %s") % error)
        if response.status_code not in (200, 201):
            raise UserError(
                _("External HR API login failed with HTTP %s.") % response.status_code
            )
        payload = self._decode_response(response)
        data = payload.get("data") if isinstance(payload, dict) else {}
        data = data if isinstance(data, dict) else {}
        token = (payload.get("token") or data.get("token")) if isinstance(payload, dict) else False
        if not token or not isinstance(token, str):
            raise UserError(_("External HR API login did not return a token."))
        self.env["ir.config_parameter"].sudo().set_param(
            "hr_management_attend_api.source_admin_token", token
        )
        config["token"] = token
        return token

    @api.model
    def _request_json(self, path, params=None, retry_auth=True):
        config = self._config()
        token = config["token"] or self._login(config)
        url = "%s/%s" % (
            self._validated_base_url(config["base_url"]),
            path.lstrip("/"),
        )
        try:
            response = self._send_request(
                "GET",
                url,
                config,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Authorization": "Bearer %s" % token,
                },
                timeout=config["timeout"],
                verify=config["verify_ssl"],
                allow_redirects=False,
            )
        except http_requests.RequestException as error:
            raise UserError(_("Could not connect to the external HR API: %s") % error)
        if response.status_code == 401 and retry_auth and config["email"] and config["password"]:
            config["token"] = ""
            self.env["ir.config_parameter"].sudo().set_param(
                "hr_management_attend_api.source_admin_token", ""
            )
            self._login(config)
            return self._request_json(path, params=params, retry_auth=False)
        if response.status_code != 200:
            raise UserError(
                _("External HR API request failed with HTTP %s.")
                % response.status_code
            )
        return self._decode_response(response)

    @api.model
    def _extract_rows(self, payload, candidate_keys):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            raise UserError(_("External HR API returned an unsupported response."))
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict) and isinstance(value.get("data"), list):
                return value["data"]
        if isinstance(payload.get("data"), list):
            return payload["data"]
        raise UserError(_("External HR API response does not contain a record list."))

    @api.model
    def _page_count(self, payload):
        if not isinstance(payload, dict):
            return None
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        data_meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        candidates = (
            meta.get("pages"),
            meta.get("last_page"),
            data_meta.get("pages"),
            data_meta.get("last_page"),
            data.get("last_page"),
            payload.get("last_page"),
        )
        for value in candidates:
            try:
                if value is not None:
                    return max(1, int(value))
            except (TypeError, ValueError):
                continue
        return None

    @api.model
    def _fetch_collection(self, path, candidate_keys, params=None):
        config = self._config()
        page_size = config["page_size"]
        page = 1
        rows = []
        previous_fingerprint = None
        while page <= 100:
            query = dict(params or {}, page=page, per_page=page_size)
            payload = self._request_json(path, params=query)
            batch = self._extract_rows(payload, candidate_keys)
            if not batch:
                break
            fingerprint = repr(
                [batch[0].get("id"), batch[-1].get("id"), len(batch)]
                if isinstance(batch[0], dict) and isinstance(batch[-1], dict)
                else [len(batch), repr(batch[0])[:100]]
            )
            if fingerprint == previous_fingerprint:
                break
            previous_fingerprint = fingerprint
            rows.extend(batch)
            pages = self._page_count(payload)
            if (pages is not None and page >= pages) or (
                pages is None and len(batch) < page_size
            ):
                break
            page += 1
        if page > 100:
            raise UserError(_("External HR API pagination exceeded 100 pages."))
        return rows

    @api.model
    def _external_id(self, value):
        if isinstance(value, dict):
            value = value.get("id")
        if value in (None, ""):
            return False
        return str(value).strip()

    @api.model
    def _number(self, value, default=0.0):
        try:
            result = float(value)
        except (TypeError, ValueError):
            return default
        return result if math.isfinite(result) else default

    @api.model
    def _boolean(self, value, default=True):
        if isinstance(value, bool):
            return value
        if value in (0, "0", "false", "False", "inactive"):
            return False
        if value in (1, "1", "true", "True", "active"):
            return True
        return default

    @api.model
    def _time_float(self, value, default):
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value) if 0 <= float(value) < 24 else default
        try:
            hours, minutes = str(value).split(":", 1)
            hours = int(hours)
            minutes = int(minutes)
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                return hours + minutes / 60
        except (TypeError, ValueError):
            pass
        return default

    @api.model
    def _sync_branches(self, config):
        if not config["sync_branches"]:
            return 0
        rows = self._fetch_collection("admin/branches", ("branches", "data"))
        model = self.env["res.branch"].sudo().with_context(active_test=False)
        synced = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_id = self._external_id(row.get("id"))
            name = str(row.get("name") or "").strip()
            if not external_id or not name:
                continue
            branch = model.search(
                [
                    ("company_id", "=", config["company"].id),
                    ("api_external_id", "=", external_id),
                ],
                limit=1,
            )
            if not branch:
                branch = model.search(
                    [
                        ("company_id", "=", config["company"].id),
                        ("name", "=", name),
                    ],
                    limit=1,
                )
            active = self._boolean(row.get("status"), True)
            values = {
                "api_external_id": external_id,
                "name": name,
                "address": row.get("address") or False,
                "api_latitude": self._number(row.get("latitude")),
                "api_longitude": self._number(row.get("longitude")),
                "api_radius_m": max(1.0, self._number(row.get("radius"), 150.0)),
                "api_morning_start": self._time_float(
                    row.get("morning_check_in_start"), 8.0
                ),
                "api_morning_end": self._time_float(
                    row.get("morning_check_in_end"), 9.0
                ),
                "api_evening_start": self._time_float(
                    row.get("evening_check_in_start"), 17.0
                ),
                "api_evening_end": self._time_float(
                    row.get("evening_check_in_end"), 18.0
                ),
                "api_grace_period_minutes": max(
                    0, int(self._number(row.get("grace_period"), 15))
                ),
                "active": active,
                "api_attendance_enabled": active,
            }
            if branch:
                update_values = {"api_external_id": external_id}
                if config["update_references"]:
                    update_values = values
                branch.write(update_values)
                synced += 1
            elif config["create_branches"]:
                values.update(
                    {
                        "company_id": config["company"].id,
                        "api_timezone": config["timezone"],
                    }
                )
                model.create(values)
                synced += 1
        return synced

    @api.model
    def _sync_employees(self, config):
        if not config["sync_employees"]:
            return 0
        rows = self._fetch_collection("admin/employees", ("employees", "data"))
        model = self.env["hr.employee"].sudo().with_context(active_test=False)
        branch_model = self.env["res.branch"].sudo().with_context(active_test=False)
        synced = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            number = str(row.get("employee_number") or "").strip()
            email = str(row.get("email") or "").strip().lower()
            if not number or not name:
                continue
            employees = model.search(
                [("api_employee_number", "=", number)],
                limit=2,
            )
            if len(employees) > 1:
                continue
            employee = employees
            branch_id = self._external_id(row.get("branch_id") or row.get("branch"))
            branch_company = employee.company_id if employee else config["company"]
            branch = branch_model.search(
                [
                    ("company_id", "=", branch_company.id),
                    ("api_external_id", "=", branch_id),
                ],
                limit=1,
            ) if branch_id else branch_model
            active = self._boolean(row.get("status"), True)
            values = {
                "name": name,
                "work_email": email or False,
                "work_phone": row.get("phone") or False,
                "job_title": row.get("position") or False,
                "api_employee_number": number or False,
                "api_branch_id": branch.id if branch else False,
                "api_hire_date": row.get("hire_date") or False,
                "active": active,
            }
            if employee:
                update_values = {"api_employee_number": number}
                if config["update_references"]:
                    update_values = values
                employee.write(update_values)
                synced += 1
            elif config["create_employees"]:
                values.update(
                    {
                        "company_id": config["company"].id,
                        "api_access_enabled": False,
                    }
                )
                model.create(values)
                synced += 1
        return synced

    @api.model
    def _parse_datetime(self, value, timezone_name):
        if not value:
            return False
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = dateutil_parser.parse(str(value))
            except (TypeError, ValueError, OverflowError):
                return False
        if parsed.tzinfo is None:
            try:
                parsed = pytz.timezone(timezone_name).localize(parsed)
            except pytz.UnknownTimeZoneError:
                parsed = pytz.utc.localize(parsed)
        return parsed.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _attendance_datetime_value(self, row, event_type, fallback_date=False):
        """Return an upstream attendance timestamp in a parseable form.

        HR2 may return a full timestamp or split the attendance date from the
        check-in/check-out time.  The pull endpoint is queried one day at a
        time, so ``fallback_date`` is safe when the row only contains a clock
        value.
        """
        if event_type == "check_in":
            value = self._row_value(
                row,
                "check_in",
                "checkIn",
                "checked_in_at",
                "checkedInAt",
                "check_in_at",
                "checkInAt",
                "clock_in",
                "checkin_at",
                "punch_in_at",
                "check_in_time",
                "checkInTime",
                "checked_in_time",
                "clock_in_time",
                "checkin_time",
                "in_time",
                "time_in",
            )
        else:
            value = self._row_value(
                row,
                "check_out",
                "checkOut",
                "checked_out_at",
                "checkedOutAt",
                "check_out_at",
                "checkOutAt",
                "clock_out",
                "checkout_at",
                "punch_out_at",
                "check_out_time",
                "checkOutTime",
                "checked_out_time",
                "clock_out_time",
                "checkout_time",
                "out_time",
                "time_out",
            )
        if isinstance(value, dict):
            value = self._row_value(
                value,
                "datetime",
                "date_time",
                "dateTime",
                "timestamp",
                "value",
                "time",
                "at",
            )
        if value in (None, ""):
            return False
        text_value = str(value).strip()
        if not _TIME_ONLY_PATTERN.match(text_value):
            return value
        attendance_date = self._row_value(
            row,
            "attendance_date",
            "attendanceDate",
            "work_date",
            "workDate",
            "record_date",
            "date",
            "day",
        ) or fallback_date
        if not attendance_date:
            return value
        if isinstance(attendance_date, datetime):
            attendance_date = attendance_date.date()
        return "%s %s" % (attendance_date, text_value)

    @api.model
    def _row_value(self, row, *names):
        for name in names:
            if row.get(name) not in (None, ""):
                return row[name]
        return False

    @api.model
    def _employee_number_for_row(self, row):
        employee_value = row.get("employee")
        number = row.get("employee_number")
        if not number and isinstance(employee_value, dict):
            number = employee_value.get("employee_number")
        return str(number or "").strip()

    @api.model
    def _employee_for_row(self, row, company):
        number = self._employee_number_for_row(row)
        model = self.env["hr.employee"].sudo().with_context(active_test=False)
        if not number:
            return model
        employees = model.search(
            [("api_employee_number", "=", number)],
            limit=2,
        )
        return employees if len(employees) == 1 else model

    @api.model
    def _branch_for_row(self, row, employee, company):
        external_id = self._external_id(row.get("branch_id") or row.get("branch"))
        branch = self.env["res.branch"].sudo().with_context(active_test=False).search(
            [
                ("company_id", "=", employee.company_id.id),
                ("api_external_id", "=", external_id),
            ],
            limit=1,
        ) if external_id else self.env["res.branch"]
        return branch or employee.api_branch_id

    @api.model
    def _event_reference(self, external_id, event_type):
        digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()[:48]
        return "external:%s:%s" % (digest, event_type)

    @api.model
    def _ensure_event(self, attendance, event_type, period, event_at, row, branch):
        if not event_at or not branch:
            return
        reference = self._event_reference(attendance.api_external_id, event_type)
        event_model = self.env["hr.attendance.api.event"].sudo()
        if event_model.search_count([("request_id", "=", reference)]):
            return
        prefix = "check_in" if event_type == "check_in" else "check_out"
        fallback_latitude = "in_latitude" if event_type == "check_in" else "out_latitude"
        fallback_longitude = "in_longitude" if event_type == "check_in" else "out_longitude"
        latitude = self._number(
            self._row_value(
                row, "%s_latitude" % prefix, "latitude", fallback_latitude
            )
        )
        longitude = self._number(
            self._row_value(
                row, "%s_longitude" % prefix, "longitude", fallback_longitude
            )
        )
        accuracy = self._number(
            self._row_value(row, "%s_accuracy" % prefix, "accuracy")
        )
        distance = self._number(
            self._row_value(row, "%s_distance" % prefix, "distance")
        )
        event_model.create(
            {
                "request_id": reference,
                "idempotency_key": reference,
                "event_type": event_type,
                "period": period,
                "event_at": event_at,
                "employee_id": attendance.employee_id.id,
                "attendance_id": attendance.id,
                "branch_id": branch.id,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
                "distance": distance,
            }
        )

    @api.model
    def _import_attendance_row(self, row, config):
        if not isinstance(row, dict):
            return "skipped", _("Attendance row is not an object.")
        external_id = self._external_id(row.get("id"))
        if not external_id:
            return "skipped", _("Attendance row has no external ID.")
        employee = self._employee_for_row(row, config["company"])
        if not employee:
            number = self._employee_number_for_row(row)
            if not number:
                return "skipped", _(
                    "External attendance row has no API Employee Number."
                )
            candidates = self.env["hr.employee"].sudo().with_context(
                active_test=False
            ).search_count([("api_employee_number", "=", number)])
            if candidates > 1:
                return "skipped", _(
                    "API Employee Number %s is duplicated across Odoo companies."
                ) % number
            return "skipped", _(
                "API Employee Number %s is not mapped in Odoo."
            ) % number
        branch = self._branch_for_row(row, employee, config["company"])
        check_in = self._parse_datetime(
            self._attendance_datetime_value(
                row, "check_in", fallback_date=config.get("pull_date")
            ),
            config["timezone"],
        )
        check_out = self._parse_datetime(
            self._attendance_datetime_value(
                row, "check_out", fallback_date=config.get("pull_date")
            ),
            config["timezone"],
        )
        if not check_in:
            return "skipped", _("Attendance row has no valid check-in time.")
        period = self._row_value(row, "shift", "check_in_period")
        period = period if period in ("morning", "evening") else "morning"
        out_period = self._row_value(row, "check_out_period", "shift")
        out_period = out_period if out_period in ("morning", "evening") else period
        model = self.env["hr.attendance"].sudo()
        attendance = model.search([("api_external_id", "=", external_id)], limit=1)
        if not attendance:
            attendance = model.search(
                [("employee_id", "=", employee.id), ("check_in", "=", check_in)],
                limit=1,
            )
        in_accuracy = self._number(
            self._row_value(row, "check_in_accuracy", "accuracy")
        )
        out_accuracy = self._number(row.get("check_out_accuracy"))
        values = {
            "api_external_id": external_id,
            "api_branch_id": branch.id if branch else False,
            "api_check_in_period": period,
            "api_check_in_accuracy": in_accuracy,
            "api_check_in_distance": self._number(
                self._row_value(row, "check_in_distance", "distance")
            ),
            "api_source": "external_sync",
        }
        if check_out:
            values.update(
                {
                    "check_out": check_out,
                    "api_check_out_period": out_period,
                    "api_check_out_accuracy": out_accuracy,
                    "api_check_out_distance": self._number(
                        row.get("check_out_distance")
                    ),
                }
            )
        if attendance:
            if attendance.employee_id != employee:
                return "skipped", _("External attendance ID belongs to another employee.")
            attendance.write(values)
            state = "updated"
        else:
            values.update({"employee_id": employee.id, "check_in": check_in})
            latitude = self._number(
                self._row_value(row, "check_in_latitude", "latitude", "in_latitude")
            )
            longitude = self._number(
                self._row_value(row, "check_in_longitude", "longitude", "in_longitude")
            )
            if "in_latitude" in model._fields:
                values.update({"in_latitude": latitude, "in_longitude": longitude})
            if check_out and "out_latitude" in model._fields:
                values.update(
                    {
                        "out_latitude": self._number(
                            self._row_value(row, "check_out_latitude", "out_latitude")
                        ),
                        "out_longitude": self._number(
                            self._row_value(row, "check_out_longitude", "out_longitude")
                        ),
                    }
                )
            attendance = model.create(values)
            state = "created"
        self._ensure_event(attendance, "check_in", period, check_in, row, branch)
        if check_out:
            self._ensure_event(attendance, "check_out", out_period, check_out, row, branch)
        return state, False

    @api.model
    def _sync_attendance_rows(self, rows, config):
        counts = {"fetched": len(rows), "created": 0, "updated": 0, "skipped": 0, "failed": 0}
        messages = []
        for index, row in enumerate(rows, 1):
            try:
                with self.env.cr.savepoint():
                    state, message = self._import_attendance_row(row, config)
                counts[state] += 1
                if message and len(messages) < 20:
                    messages.append("Row %s: %s" % (index, message))
            except Exception as error:
                counts["failed"] += 1
                if len(messages) < 20:
                    messages.append("Row %s: %s" % (index, str(error)[:300]))
                _logger.warning("External attendance row import failed", exc_info=True)
        return counts, messages

    @api.model
    def _test_connection(self):
        payload = self._request_json("me")
        if not isinstance(payload, dict):
            raise UserError(_("External HR API returned an invalid profile response."))
        return payload

    @api.model
    def _run_sync(
        self,
        date_from,
        date_to,
        trigger="manual",
        branch=None,
        employee=None,
        shift=None,
    ):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to or date_from > date_to:
            raise UserError(_("Choose a valid synchronization date range."))
        if (date_to - date_from).days > 366:
            raise UserError(_("A single synchronization cannot exceed 366 days."))
        config = self._config()
        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock(%s)", (_SYNC_ADVISORY_LOCK_KEY,)
        )
        lock_acquired = bool(self.env.cr.fetchone()[0])
        now = fields.Datetime.now()
        log = self.env["hr.attendance.api.sync.log"].sudo().create(
            {
                "name": _("Attendance sync %s to %s") % (date_from, date_to),
                "company_id": config["company"].id,
                "trigger": trigger,
                "date_from": date_from,
                "date_to": date_to,
                "branch_id": branch.id if branch else False,
                "employee_id": employee.id if employee else False,
                "shift": shift or False,
                "started_at": now,
            }
        )
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param(
            "hr_management_attend_api.source_last_attempt_at",
            fields.Datetime.to_string(now),
        )
        if not lock_acquired:
            log.write(
                {
                    "state": "skipped",
                    "finished_at": fields.Datetime.now(),
                    "message": _(
                        "Another attendance synchronization is already running."
                    ),
                }
            )
            return log
        totals = {"fetched": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}
        messages = []
        try:
            successful_days = 0
            branch_count = 0
            employee_count = 0
            try:
                branch_count = self._sync_branches(config)
            except Exception as error:
                totals["failed"] += 1
                messages.append(_("Branch refresh failed: %s") % str(error)[:300])
                _logger.warning("External branch refresh failed", exc_info=True)
            try:
                employee_count = self._sync_employees(config)
            except Exception as error:
                totals["failed"] += 1
                messages.append(_("Employee refresh failed: %s") % str(error)[:300])
                _logger.warning("External employee refresh failed", exc_info=True)
            current = date_from
            while current <= date_to:
                try:
                    with self.env.cr.savepoint():
                        query = {"date": fields.Date.to_string(current)}
                        if branch:
                            query["branch_id"] = branch.api_external_id
                        if employee:
                            query["employee_number"] = employee.api_employee_number
                        if shift:
                            query["shift"] = shift
                        rows = self._fetch_collection(
                            "admin/attendances",
                            ("attendances", "data"),
                            params=query,
                        )
                        day_config = dict(
                            config, pull_date=fields.Date.to_string(current)
                        )
                        counts, row_messages = self._sync_attendance_rows(
                            rows, day_config
                        )
                    successful_days += 1
                    for key in totals:
                        totals[key] += counts[key]
                    messages.extend(row_messages[: max(0, 20 - len(messages))])
                except Exception as error:
                    totals["failed"] += 1
                    if len(messages) < 20:
                        messages.append(
                            _("Date %s failed: %s") % (current, str(error)[:300])
                        )
                    _logger.warning(
                        "External attendance date %s failed", current, exc_info=True
                    )
                current += timedelta(days=1)
            if successful_days == 0:
                state = "failed"
            else:
                state = "partial" if totals["failed"] or totals["skipped"] else "success"
            finished_at = fields.Datetime.now()
            log.write(
                {
                    "state": state,
                    "finished_at": finished_at,
                    "fetched_count": totals["fetched"],
                    "created_count": totals["created"],
                    "updated_count": totals["updated"],
                    "skipped_count": totals["skipped"],
                    "failed_count": totals["failed"],
                    "branch_count": branch_count,
                    "employee_count": employee_count,
                    "message": "\n".join(messages) or False,
                }
            )
            if state in ("success", "partial"):
                completed_at = fields.Datetime.to_string(finished_at)
                parameters.set_param(
                    "hr_management_attend_api.source_last_sync_at", completed_at
                )
                parameters.set_param(
                    "hr_management_attend_api.source_last_success_at", completed_at
                )
                parameters.set_param(
                    "hr_management_attend_api.source_consecutive_failures", "0"
                )
            else:
                failures = self._integer_parameter(
                    "source_consecutive_failures", 0, minimum=0
                )
                parameters.set_param(
                    "hr_management_attend_api.source_consecutive_failures",
                    str(failures + 1),
                )
        except Exception as error:
            log.write(
                {
                    "state": "failed",
                    "finished_at": fields.Datetime.now(),
                    "message": str(error)[:2000],
                }
            )
            failures = self._integer_parameter(
                "source_consecutive_failures", 0, minimum=0
            )
            parameters.set_param(
                "hr_management_attend_api.source_consecutive_failures",
                str(failures + 1),
            )
            _logger.exception("External attendance synchronization failed")
        return log

    @api.model
    def _cron_pull_attendance(self):
        if not self._boolean_parameter("source_auto_sync", False):
            return
        lookback = self._integer_parameter("source_lookback_days", 2, maximum=31)
        timezone_name = self._parameter("source_timezone", "Asia/Riyadh")
        try:
            timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            timezone = pytz.utc
        today = datetime.now(pytz.utc).astimezone(timezone).date()
        self._run_sync(
            today - timedelta(days=lookback - 1),
            today,
            trigger="cron",
        )
