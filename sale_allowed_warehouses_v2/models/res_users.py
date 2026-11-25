from odoo import models, fields

class ResUsers(models.Model):
    _inherit = "res.users"

    # Let Odoo generate relation table automatically (avoid FK issues)
    allowed_warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse",
        string="Allowed Warehouses",
    )
