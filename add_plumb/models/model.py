from odoo import models, fields, api


class AddPlumberField(models.Model):
    _inherit = 'account.payment'

    plumber_id = fields.Many2one(comodel_name="plumber.plumber", string='Plumber/السباك')


class AddPlumberFieldInAccountMove(models.Model):
    _inherit = 'account.move'

    plumber_id = fields.Many2one(comodel_name="plumber.plumber", string='Plumber/السباك')