# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Vishnu K P (odoo@cybrosys.com)
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
from odoo import api, models, fields


class StockPicking(models.Model):
    """Extends stock picking to apply domain restrictions based on user's
    assigned warehouses."""
    _inherit = 'stock.picking'

    @api.onchange('location_id', 'location_dest_id')
    def _onchange_location_id(self):
        """Domain for location_id and location_dest_id."""
        if self.env['ir.config_parameter'].sudo().get_param(
                'user_warehouse_restriction.group_user_warehouse_restriction'):
            return {
                'domain': {'location_id': [
                    ('warehouse_id.user_ids', 'in', self.env.user.id)],
                    'location_dest_id': [
                        ('warehouse_id.user_ids', 'in', self.env.user.id)]}}


class SaleOrderInh(models.Model):
    _inherit = 'sale.order'

    @api.depends('user_id', 'company_id')
    def _compute_warehouse_id(self):
        for order in self:
            default_warehouse_id = self.env['stock.warehouse'].search([]).filtered(
                lambda i: self.env.user.id in i.user_ids.ids)
            if default_warehouse_id:
                order.warehouse_id = default_warehouse_id[0]
