from odoo import fields, models


class ExecutiveIntelligenceAccessProfile(models.Model):
    _inherit = "executive.intelligence.access.profile"

    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "ei_profile_warehouse_rel",
        "profile_id",
        "warehouse_id",
        string="Analytics Warehouses",
    )

