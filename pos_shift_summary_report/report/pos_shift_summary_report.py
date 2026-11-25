from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosShiftSummaryReport(models.AbstractModel):
    _name = "report.pos_shift_summary_report.report_pos_shift_summary"
    _description = "POS Shift Summary Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard_ids = docids or [(data or {}).get("wizard_id")]
        wizard = self.env["pos.shift.summary.report.wizard"].browse(
            [wizard_id for wizard_id in wizard_ids if wizard_id]
        ).exists()
        wizard.ensure_one()
        report_data = wizard._prepare_report_data()
        return {
            "doc_ids": wizard.ids,
            "doc_model": wizard._name,
            "docs": wizard,
            "wizard": wizard,
            "lang": "ar_001",
            **report_data,
        }


class PosSessionShiftSummaryReport(models.AbstractModel):
    _name = "report.pos_shift_summary_report.session_shift"
    _description = "POS Session Shift Summary Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        sessions = self.env["pos.session"].browse(docids).exists()
        sessions.ensure_one()
        sessions.check_access_rights("read")
        sessions.check_access_rule("read")
        if not sessions.start_at:
            raise UserError(_("The POS session has no opening date."))

        report_end = sessions.stop_at or fields.Datetime.now()

        timezone = self.env.context.get("tz") or self.env.user.tz or "UTC"
        wizard = (
            self.env["pos.shift.summary.report.wizard"]
            .sudo()
            .with_context(tz=timezone)
            .create(
                {
                    "company_id": sessions.company_id.id,
                    "pos_config_ids": [(6, 0, sessions.config_id.ids)],
                    "session_ids": [(6, 0, sessions.ids)],
                    "date_from": sessions.start_at,
                    "date_to": report_end,
                }
            )
        )
        report_data = wizard._prepare_report_data()
        return {
            "doc_ids": sessions.ids,
            "doc_model": sessions._name,
            "docs": sessions,
            "wizard": wizard,
            "lang": "ar_001",
            **report_data,
        }
