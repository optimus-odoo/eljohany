from odoo import SUPERUSER_ID, api


def _translate(record, field_name, value, lang):
    if record:
        record.with_context(lang=lang).write({field_name: value})


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    language = env["res.lang"].search(
        [("code", "=", "ar_001"), ("active", "=", True)],
        limit=1,
    )
    if not language:
        return

    menu_names = {
        "ohrms_loan.employee_forms_menu_root": "النماذج",
        "ohrms_loan.hr_loan_menu_category": "السلف",
        "ohrms_loan.hr_loan_menu_root": "طلباتي",
        "ohrms_loan.hr_loan_approval_menu": "الموافقات",
        "ohrms_loan.hr_loan_management_menu": "الإدارة",
        "ohrms_loan.hr_loan_workflow_menu": "مسارات الموافقات",
    }
    for xmlid, arabic_name in menu_names.items():
        _translate(
            env.ref(xmlid, raise_if_not_found=False),
            "name",
            arabic_name,
            language.code,
        )

    for xmlid in (
        "ohrms_loan.hr_loan_menu",
        "ohrms_loan.hr_loan_menu_requests",
    ):
        legacy_menu = env.ref(xmlid, raise_if_not_found=False)
        if legacy_menu:
            legacy_menu.active = False

    action_names = {
        "ohrms_loan.hr_loan_action": "طلبات السلف الخاصة بي",
        "ohrms_loan.hr_loan_approval_action": "طلبات السلف بانتظار إجرائي",
        "ohrms_loan.hr_loan_management_action": "إدارة السلف",
        "ohrms_loan.hr_loan_workflow_action": "مسارات موافقات السلف",
        "ohrms_loan.act_hr_employee_loan_request": "السلف",
    }
    for xmlid, arabic_name in action_names.items():
        _translate(
            env.ref(xmlid, raise_if_not_found=False),
            "name",
            arabic_name,
            language.code,
        )

    field_names = {
        ("hr.loan", "name"): "رقم طلب السلفة",
        ("hr.loan", "loan_amount"): "مبلغ السلفة",
        ("hr.loan", "installment"): "عدد الأقساط",
        ("hr.loan", "payment_date"): "تاريخ بدء السداد",
        ("hr.loan", "loan_lines"): "أقساط السلفة",
        ("hr.loan", "state"): "الحالة",
        ("hr.loan.approval.line", "sequence"): "التسلسل",
        ("hr.loan.approval.line", "status"): "الحالة",
        ("hr.payslip", "loan_due_amount"): "المبلغ المستحق من السلفة",
        ("hr.payslip", "loan_due_count"): "عدد الأقساط المستحقة",
    }
    for (model_name, field_name), arabic_name in field_names.items():
        field = env["ir.model.fields"]._get(model_name, field_name)
        _translate(field, "field_description", arabic_name, language.code)

    selection_names = {
        ("hr.loan.approval.line", "status", "pending"): "قيد الانتظار",
        ("hr.loan.approval.line", "status", "waiting"): "بانتظار الإجراء",
        ("hr.loan.approval.line", "status", "approved"): "معتمد",
        ("hr.loan.approval.line", "status", "rejected"): "مرفوض",
        ("hr.loan.approval.line", "status", "cancelled"): "ملغي",
    }
    for (model_name, field_name, value), arabic_name in selection_names.items():
        field = env["ir.model.fields"]._get(model_name, field_name)
        selection = env["ir.model.fields.selection"].search(
            [("field_id", "=", field.id), ("value", "=", value)],
            limit=1,
        )
        _translate(selection, "name", arabic_name, language.code)
