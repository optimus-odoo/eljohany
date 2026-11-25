{
    "name": "Eljohany Executive Intelligence Core",
    "summary": "Secure, user-scoped executive intelligence center",
    "version": "17.0.1.4.1",
    "category": "Productivity/Business Intelligence",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/executive_intelligence_security.xml",
        "security/ir.model.access.csv",
        "data/executive_dashboard_data.xml",
        "data/default_configuration.xml",
        "views/res_users_views.xml",
        "views/access_profile_views.xml",
        "views/access_log_views.xml",
        "views/executive_intelligence_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "eljohany_executive_intelligence_core/static/src/js/executive_intelligence_center.js",
            "eljohany_executive_intelligence_core/static/src/xml/executive_intelligence_center.xml",
            "eljohany_executive_intelligence_core/static/src/scss/executive_intelligence_center.scss",
        ],
    },
    "installable": True,
    "application": True,
}

