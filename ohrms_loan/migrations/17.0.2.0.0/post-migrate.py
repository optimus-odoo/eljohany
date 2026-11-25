from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in (
        "ohrms_loan.hr_loan_rule_company",
        "ohrms_loan.hr_loan_rule_user",
        "ohrms_loan.hr_loan_rule_employee",
    ):
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule:
            rule.active = False
    for xmlid in (
        "ohrms_loan.access_hr_loan_user",
        "ohrms_loan.access_hr_job_user",
        "ohrms_loan.access_hr_loan_line_user",
    ):
        access = env.ref(xmlid, raise_if_not_found=False)
        if access:
            access.active = False
