# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2019 EquickERP
#
##############################################################################

from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.onchange('warehouse_id')
    def onchange_warehouse_location(self):
        for line in self.order_line:
            line.onchange_get_product_id_location()


class sale_order_line(models.Model):
    _inherit = 'sale.order.line'

    stock_location_id = fields.Many2one('stock.location', string="Location")

    @api.onchange('product_id')
    def onchange_get_product_id_location(self):
        location_id = False
        warehouse_id = self.order_id.warehouse_id
        if self.product_id and warehouse_id:
            location_id = warehouse_id.lot_stock_id.id
            locations = self.env['stock.location'].search([('id', 'child_of', [warehouse_id.view_location_id.id])])
            domain = ' location_id in %s AND quantity != 0 AND active = TRUE AND product_id = %s'
            args = (tuple(locations.ids), self.product_id.id,)
            self.env.cr.execute("""SELECT location_id
                                   FROM stock_quant
                                   LEFT JOIN product_product ON product_product.id = stock_quant.product_id
                                   WHERE %s GROUP BY location_id""" % domain, args)
            result = self.env.cr.dictfetchall()
            if result: location_id = result[0]['location_id']
        self.stock_location_id = location_id


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values):
        move_values = super(StockRule, self)._get_stock_move_values(product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values)
        if move_values and values.get('sale_line_id'):
            sol_id = self.env['sale.order.line'].browse(values['sale_line_id'])
            if sol_id and sol_id.stock_location_id:
                move_values.update({'location_id': sol_id.stock_location_id.id})
        return move_values


class stock_location(models.Model):
    _inherit = 'stock.location'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        context = self.env.context
        if context.get('from_so_line_warehouse'):
            stock_warehouse_id = self.env['stock.warehouse'].browse(context.get('from_so_line_warehouse'))
            domain += [('location_id', 'child_of', stock_warehouse_id.view_location_id.id)]
        return super(stock_location, self)._name_search(name, domain=domain, operator=operator, limit=limit, order=order)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: