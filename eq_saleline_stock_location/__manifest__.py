# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2019 EquickERP
#
##############################################################################

{
    'name': "Product Sales by Location",
    'category': 'Sales',
    'version': '17.0.1.0',
    'author': 'Equick ERP',
    'description': """
         This module allows users to set a location on sale order line.
         * Whatever location is selected on sale order lines, the product will be delivered from the selected location.
         * Delivery orders will be created based on selected location on sale order lines.
    """,
    'summary': """sale product by location sale products by location product sale by location selection on sale line location product deliver location sale order product deliver location on sale order location wise delivery order Sale Product Quantity Location wise""",
    'depends' : ['base', 'sale_management', 'sale_stock'],
    'price': 15,
    'currency': 'EUR',
    'license': 'OPL-1',
    'website': "",
    'data': [
        'views/sale_order_view.xml',
        'views/sale_report_template.xml'
    ],
    'images': ['static/description/main_screenshot.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'pre_init_hook': 'module_install_hook'
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: