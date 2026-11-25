{
    'name': 'Approve Partner Credit Limit',
    'version': '17.0.0.2',
    'summary': 'Manage and approve partner credit limits in sales orders.',
    'description': """
This module allows users to set, manage, and approve customer credit limits in sales orders.
It provides approval workflows and prevents order confirmation if the credit limit is exceeded,
unless approved by an authorized user.
""",
    'category': 'Sales',
    'author': 'Mohamed Mohsen',
    'website': 'mohamedmohsen1809@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'sale', 'edit_sale_order'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
