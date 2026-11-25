from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy_rule = env.ref(
        "ohrms_loan_accounting.hr_loan_rule_manager",
        raise_if_not_found=False,
    )
    if legacy_rule:
        legacy_rule.active = False
    for xmlid in (
        "ohrms_loan_accounting.access_account_move_uinvoice_officer",
        "ohrms_loan_accounting.access_account_journal_uinvoice_officer",
        "ohrms_loan_accounting.acces_account_move_line_officer",
        "ohrms_loan_accounting.access_account_move_uinvoice_manager",
        "ohrms_loan_accounting.access_account_journal_uinvoice_manager",
        "ohrms_loan_accounting.acces_account_move_line_manager",
    ):
        access = env.ref(xmlid, raise_if_not_found=False)
        if access:
            access.active = False
