{
    "name": "Eljohany Fleet Documents",
    "version": "17.0.1.0.1",
    "category": "Human Resources/Fleet",
    "summary": "Company vehicle documents, accident files, and expiry reminders",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["fleet", "mail", "branch"],
    "data": [
        "security/ir.model.access.csv",
        "security/fleet_vehicle_accident_rules.xml",
        "data/fleet_document_cron.xml",
        "data/fleet_view_repairs.xml",
        "views/fleet_vehicle_views.xml",
        "views/fleet_vehicle_accident_views.xml",
    ],
    "installable": True,
    "application": False,
}
