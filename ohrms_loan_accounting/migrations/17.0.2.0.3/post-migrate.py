from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    language = env["res.lang"].search(
        [("code", "=", "ar_001"), ("active", "=", True)],
        limit=1,
    )
    if not language:
        return
    journal_field = env["ir.model.fields"]._get("hr.loan", "journal_id")
    if journal_field:
        journal_field.with_context(lang=language.code).field_description = (
            "دفتر اليومية"
        )
