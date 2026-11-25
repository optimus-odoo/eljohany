# -*- coding: utf-8 -*-
#############################################################################
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2023-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
{
    'name': 'Open HRMS Loan Management',
    'version': '17.0.2.1.0',
    'category': 'Human Resources',
    'summary': 'Manage employee loans with the official Odoo payroll engine',
    'description': (
        'Create and manage employee loan requests and deduct installments '
        'automatically from payroll.'
    ),
    'author': "Cybrosys Techno Solutions,Open HRMS",
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'live_test_url': 'https://youtu.be/lAT5cqVZTZI',
    'website': "https://cybrosys.com, https://www.openhrms.com",
    'depends': ['hr', 'account', 'hr_payroll'],
    'data': [
        'security/hr_loan_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/hr_payroll_data.xml',
        'views/hr_loan_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_views.xml',
    ],
    'images': ['static/description/banner.jpg'],
    'license': 'LGPL-3',
    # Ported to the official payroll engine. Do not add hr_payroll_community:
    # loading both payroll implementations breaks registry model setup.
    'installable': True,
    'auto_install': False,
    'application': False,
}
