from odoo import api, fields, models




class StockQuant(models.Model):
    _inherit = 'stock.quant'

    stock_cost = fields.Float(string="Cost", related="product_id.standard_price")
    stock_total_cost = fields.Float(string="Total Cost", compute="_compute_stock_total_cost", store=True)

    @api.depends('stock_cost', 'inventory_quantity')
    def _compute_stock_total_cost(self):
        for quant in self:
            quant.stock_total_cost = quant.stock_cost * quant.inventory_quantity
