# -*- coding: utf-8 -*-

{
    "name": "Company Switcher Select All",
    "version": "17.0.1.0.0",
    "category": "Productivity",
    "summary": "Select or clear all allowed companies from the Odoo company switcher",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "eljohany_company_switcher_select_all/static/src/js/company_switcher_select_all.js",
            "eljohany_company_switcher_select_all/static/src/xml/company_switcher_select_all.xml",
            "eljohany_company_switcher_select_all/static/src/scss/company_switcher_select_all.scss",
        ],
        "web.assets_unit_tests": [
            (
                "eljohany_company_switcher_select_all/static/src/js/"
                "company_switcher_select_all.js"
            ),
            "eljohany_company_switcher_select_all/static/tests/company_switcher_select_all_tests.js",
        ],
    },
    "installable": True,
    "application": False,
}
