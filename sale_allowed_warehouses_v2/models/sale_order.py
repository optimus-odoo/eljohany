from odoo import api, fields, models
from odoo.fields import Command

class SaleOrder(models.Model):
    _inherit = "sale.order"

    available_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        compute="_compute_available_warehouse_ids",
        store=False,
    )

    
    @api.depends("company_id")
    def _compute_available_warehouse_ids(self):
        user = self.env.user
        Warehouse = self.env["stock.warehouse"]
        for order in self:
            whs = Warehouse
            if order.company_id:
                # If user has allowed warehouses -> only those (within company)
                if user.allowed_warehouse_ids:
                    whs = user.allowed_warehouse_ids.filtered(lambda w: w.company_id == order.company_id)
                else:
                    # If not assigned -> show all warehouses in the company
                    whs = Warehouse.search([("company_id", "=", order.company_id.id)])
            order.available_warehouse_ids = [Command.set(whs.ids)]



class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    available_stock_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_available_stock_location_ids",
        store=False,
    )

    @api.depends("order_id.company_id")
    def _compute_available_stock_location_ids(self):
        user = self.env.user
        Location = self.env["stock.location"]

        for line in self:
            locs = Location
            company = line.order_id.company_id

            if not company:
                line.available_stock_location_ids = [Command.clear()]
                continue

            # لو المستخدم عنده allowed warehouses
            if user.allowed_warehouse_ids:
                warehouses = user.allowed_warehouse_ids.filtered(
                    lambda w: w.company_id == company
                )

                # كل الـ internal locations التابعة لمخازنهم
                locs = Location.search([
                    ("usage", "=", "internal"),
                    ("warehouse_id", "in", warehouses.ids),
                ])
            else:
                # لو ما عنده تعيين → كل internal locations للشركة
                locs = Location.search([
                    ("usage", "=", "internal"),
                    "|",
                    ("company_id", "=", company.id),
                    ("company_id", "=", False),
                ])

            line.available_stock_location_ids = [Command.set(locs.ids)]
