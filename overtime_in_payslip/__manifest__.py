# -*- coding: utf-8 -*-
{
    'name': 'Bonus',

    'version': '17.0.1.8',
    'summary': 'Overtime in Payslip',
    'description': """ Overtime in Payslip For HR)""",
    'author': 'DeeB',
    'website': "",
    'category': 'human resource',
    'depends': ['base', 'hr_payroll', 'hr_employees_operations_menu', 'hr_attendance'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/hr_contract.xml',
        'views/bonus_type.xml',
        'views/employee_bonus.xml',
        'views/hr_payslip.xml',
        'views/salary_rule.xml',
        'wizard/bonus_deduction_report_wizard_view.xml',
        'views/employee_bonus_deduction_report_doc.xml',
        'report/employee_bonus_deduction_report.xml',
        'views/menu.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
    ],
    'assets': {
        "web.assets_frontend": [
            # to add scss and js here
        ],
        "web.assets_qweb": [
            # to add templates here
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
