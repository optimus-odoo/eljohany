from odoo import fields, models, api


class OvertimeType(models.Model):
    _name = 'overtime.type'

    name = fields.Char(required=True)
    rate = fields.Float(default=1,
        string='Rate',
        required=False)
