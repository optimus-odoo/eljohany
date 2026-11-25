from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields


def _as_boolean(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    parameters = env["ir.config_parameter"].sudo()
    enabled = _as_boolean(
        parameters.get_param("hr_management_attend_api.source_auto_sync", "False")
    )
    try:
        interval = int(
            parameters.get_param(
                "hr_management_attend_api.source_interval_minutes", "15"
            )
        )
    except (TypeError, ValueError):
        interval = 15
    interval = max(5, min(interval, 1440))

    pull_cron = env.ref(
        "hr_management_attend_api.ir_cron_pull_external_attendance",
        raise_if_not_found=False,
    )
    if pull_cron:
        values = {
            "active": enabled,
            "interval_number": interval,
            "interval_type": "minutes",
            "numbercall": -1,
            "doall": False,
        }
        if enabled:
            values["nextcall"] = fields.Datetime.now() + timedelta(minutes=1)
        pull_cron.sudo().write(values)

    cleanup_cron = env.ref(
        "hr_management_attend_api.ir_cron_cleanup_attendance_api_tokens",
        raise_if_not_found=False,
    )
    if cleanup_cron:
        cleanup_cron.sudo().write(
            {"active": True, "numbercall": -1, "doall": False}
        )
