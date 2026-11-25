import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class ExecutiveIntelligenceService(models.AbstractModel):
    _name = "executive.intelligence.service"
    _description = "Executive Intelligence Service"

    _EI_CHART_TYPES = {
        "line",
        "area",
        "bar",
        "column",
        "gauge",
        "progress",
        "heatmap",
        "geo",
    }

    def _ei_assert_center_access(self):
        if not self.env.user.has_group(
            "eljohany_executive_intelligence_core.group_ei_user"
        ):
            raise AccessError(_("You are not allowed to access the intelligence center."))

    def _ei_supported_dashboard_codes(self):
        """Return dashboard codes backed by installed provider modules.

        Provider modules extend this set. Merely having an Odoo business app
        installed must never expose a dashboard without a real data provider.
        """
        return set()

    def _ei_available_dashboards(self, access):
        allowed_ids = set(access["dashboard_ids"])
        supported_codes = self._ei_supported_dashboard_codes()
        dashboards = self.env["executive.intelligence.dashboard"].sudo().search(
            [("active", "=", True)], order="sequence, id"
        )
        # Keep the administrative metadata environment. Dashboard definitions do
        # not contain business data, while ordinary viewers deliberately have no
        # direct ACL on this configuration model.
        result = dashboards.browse()
        for dashboard in dashboards:
            if (
                dashboard.id in allowed_ids
                and dashboard.code in supported_codes
                and dashboard.is_available()
            ):
                if dashboard.sensitivity == "financial" and access[
                    "financial_access"
                ] == "none":
                    continue
                if dashboard.sensitivity == "hr" and access["hr_access"] == "none":
                    continue
                if dashboard.sensitivity == "payroll" and access[
                    "hr_access"
                ] != "payroll":
                    continue
                if dashboard.code == "forecast" and not access["can_forecast"]:
                    continue
                result |= dashboard
        return result

    def _ei_get_dashboard(self, code, access):
        dashboards = self._ei_available_dashboards(access)
        dashboard = dashboards.filtered(lambda item: item.code == code)
        if not dashboard:
            raise AccessError(_("You are not allowed to access this dashboard."))
        return dashboard[:1]

    def _ei_normalize_filters(self, filters, access):
        filters = dict(filters or {})
        allowed_companies = set(access["company_ids"])
        requested_companies = (
            filters["company_ids"]
            if "company_ids" in filters
            else sorted(allowed_companies)
        )
        try:
            requested_companies = {int(company_id) for company_id in requested_companies}
        except (TypeError, ValueError) as error:
            raise UserError(_("Invalid company filter.")) from error
        if not requested_companies or not requested_companies <= allowed_companies:
            raise AccessError(_("The selected company scope is not allowed."))

        today = fields.Date.context_today(self)
        default_start = today - timedelta(days=29)
        try:
            date_from = fields.Date.to_date(filters.get("date_from") or default_start)
            date_to = fields.Date.to_date(filters.get("date_to") or today)
        except (TypeError, ValueError) as error:
            raise UserError(_("Invalid date filter.")) from error
        if not date_from or not date_to or date_from > date_to:
            raise UserError(_("The start date must not be after the end date."))
        if (date_to - date_from).days > 3660:
            raise UserError(_("The selected period is too large."))
        return {
            "company_ids": sorted(requested_companies),
            "date_from": date_from,
            "date_to": date_to,
        }

    def _ei_period_comparison(self, current, previous, positive_is_good=True):
        """Build an explicit, auditable previous-period KPI comparison."""
        current = float(current or 0.0)
        previous = float(previous or 0.0)
        difference = current - previous
        if previous:
            percent = (difference / abs(previous)) * 100
            display = f"{percent:+,.1f}%"
        elif current:
            percent = None
            display = _("New")
        else:
            percent = 0.0
            display = "0.0%"
        direction = (
            "up" if difference > 0 else ("down" if difference < 0 else "flat")
        )
        beneficial = difference > 0 if positive_is_good else difference < 0
        harmful = difference < 0 if positive_is_good else difference > 0
        tone = "success" if beneficial else ("danger" if harmful else "neutral")
        return {
            "label": _("vs previous period"),
            "display": display,
            "percent": percent,
            "direction": direction,
            "tone": tone,
            "current": current,
            "previous": previous,
        }

    def _ei_validate_visual_payload(self, payload):
        """Fail early when a provider returns an unsafe or malformed visual."""
        if not isinstance(payload, dict):
            raise UserError(_("The dashboard provider returned an invalid payload."))
        for collection in ("cards", "charts", "tables"):
            payload.setdefault(collection, [])
            if not isinstance(payload[collection], list):
                raise UserError(
                    _("Dashboard collection '%s' must be a list.") % collection
                )
        for chart in payload["charts"]:
            if (
                not isinstance(chart, dict)
                or chart.get("type") not in self._EI_CHART_TYPES
            ):
                raise UserError(
                    _("The dashboard provider returned an unsupported chart.")
                )
            if not chart.get("key") or not chart.get("title"):
                raise UserError(_("Every chart must have a key and a title."))
            items = chart.setdefault("items", [])
            if not isinstance(items, list):
                raise UserError(_("Chart items must be a list."))
            for item in items:
                value = item.get("value", 0.0)
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise UserError(_("Chart values must be finite numbers."))
                for optional_number in ("target", "percent"):
                    candidate = item.get(optional_number)
                    if candidate is not None and (
                        not isinstance(candidate, (int, float))
                        or not math.isfinite(candidate)
                    ):
                        raise UserError(_("Chart values must be finite numbers."))
                if chart["type"] == "geo":
                    latitude = item.get("latitude")
                    longitude = item.get("longitude")
                    if (
                        not isinstance(latitude, (int, float))
                        or not isinstance(longitude, (int, float))
                        or not math.isfinite(latitude)
                        or not math.isfinite(longitude)
                        or not -90 <= latitude <= 90
                        or not -180 <= longitude <= 180
                    ):
                        raise UserError(_("Geographic chart coordinates are invalid."))
        return payload

    @api.model
    def get_bootstrap(self):
        self._ei_assert_center_access()
        access = self.env.user._ei_effective_access()
        dashboards = self._ei_available_dashboards(access)
        companies = self.env["res.company"].browse(access["company_ids"]).exists()
        return {
            "dashboards": [
                {
                    "id": dashboard.id,
                    "code": dashboard.code,
                    "name": dashboard.name,
                    "icon": dashboard.icon,
                    "sensitivity": dashboard.sensitivity,
                }
                for dashboard in dashboards
            ],
            "companies": [
                {
                    "id": company.id,
                    "name": company.name,
                    "currency_id": company.currency_id.id,
                    "currency_name": company.currency_id.name,
                }
                for company in companies
            ],
            "permissions": {
                key: access[key]
                for key in (
                    "financial_access",
                    "hr_access",
                    "can_drilldown",
                    "can_export",
                    "can_forecast",
                    "can_manage_alerts",
                    "can_manage_kpis",
                )
            },
            "today": fields.Date.context_today(self),
        }

    @api.model
    def get_dashboard_data(self, dashboard_code, filters=None):
        self._ei_assert_center_access()
        access = self.env.user._ei_effective_access()
        dashboard = self._ei_get_dashboard(dashboard_code, access)
        normalized = self._ei_normalize_filters(filters, access)
        service = self.with_context(allowed_company_ids=normalized["company_ids"])
        payload = service._ei_get_dashboard_data(dashboard.code, normalized, access)
        payload = service._ei_validate_visual_payload(payload)
        payload.setdefault("status", "ok")
        payload["dashboard"] = {
            "code": dashboard.code,
            "name": dashboard.name,
        }
        payload["filters"] = {
            "company_ids": normalized["company_ids"],
            "date_from": fields.Date.to_string(normalized["date_from"]),
            "date_to": fields.Date.to_string(normalized["date_to"]),
        }
        if "warehouse_ids" in normalized:
            payload["filters"]["warehouse_ids"] = normalized["warehouse_ids"]
        payload["generated_at"] = fields.Datetime.to_string(fields.Datetime.now())
        return payload

    def _ei_get_dashboard_data(self, dashboard_code, filters, access):
        return {
            "status": "provider_not_installed",
            "message": _("This dashboard data provider is not installed yet."),
            "cards": [],
            "charts": [],
            "tables": [],
        }

