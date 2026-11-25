# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    delivered_qty_inventory = fields.Float(copy=False, readonly=True, string='Delivered QTY')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    credit_note_id = fields.Many2one(comodel_name="stock.picking")

    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        for line in self.move_ids_without_package:
            line.credit_line_id.delivered_qty_inventory = line.quantity
        return res


class StockMove(models.Model):
    _inherit = 'stock.move'

    credit_line_id = fields.Many2one(comodel_name="account.move.line")


class AccountMoveInh(models.Model):
    _inherit = 'account.move'

    location_id = fields.Many2one(comodel_name="stock.location", domain="[('usage', '=', 'internal')]")
    plumber_id = fields.Many2one(comodel_name="plumber.plumber", string="Plumper/سباك")
    create_operation = fields.Boolean(copy=False)

    def button_create_vendor_return(self):
        for rec in self:
            # منع التكرار
            if rec.create_operation or rec.reversal_move_id:
                raise UserError(_("You cannot create a return twice for the same invoice."))
    
            if not rec.location_id:
                raise UserError(_("Kindly set location first."))
    
            # تحقق شركات
            company = rec.partner_id.company_id | rec.location_id.company_id | rec.company_id | rec.invoice_line_ids.product_id.company_id
            if len(company) > 1:
                raise UserError(_("Multi-company conflict: Vendor, Location, Invoice, or Product does not belong to the same company."))
    
            # Operation type: Outgoing (Delivery) from the same warehouse
            operation_type = self.env["stock.picking.type"].search([
                ("code", "=", "outgoing"),
                ("warehouse_id", "=", rec.location_id.warehouse_id.id)
            ], limit=1)
    
            if not operation_type:
                raise UserError(
                    _("Create an Operation Type (Outgoing) with the warehouse of the selected location: %s.")
                    % rec.location_id.warehouse_id.name
                )
    
            # Locations
            # source: your stock location (internal)
            source_location = rec.location_id
    
            # destination: vendor location
            vendor_location = rec.partner_id.property_stock_supplier
            if not vendor_location:
                # fallback (usually exists)
                vendor_location = self.env.ref("stock.stock_location_suppliers")
    
            move_lines = []
            for line in rec.invoice_line_ids:
                # optional: skip non-stockable
                if line.product_id.type not in ("product", "consu"):
                    continue
    
                move_lines.append((0, 0, {
                    "name": line.product_id.display_name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.quantity,
                    "product_uom": line.product_uom_id.id if line.product_uom_id else line.product_id.uom_id.id,
                    "location_id": source_location.id,
                    "location_dest_id": vendor_location.id,
                    "credit_line_id": line.id,  # keep your link
                }))
    
            if not move_lines:
                raise UserError(_("No stockable lines to return."))
    
            picking_vals = {
                "partner_id": rec.partner_id.id,
                "picking_type_id": operation_type.id,
                "move_type": "one",
                "location_id": source_location.id,
                "location_dest_id": vendor_location.id,
                "origin": "Vendor Return - %s" % rec.name,
                "move_ids_without_package": move_lines,
            }
    
            picking = self.env["stock.picking"].create(picking_vals)
            picking.action_confirm()
    
            # نفس منطقك (لكن هذا السطر عندك غلط غالباً)
            # operation.credit_note_id = operation.id  <-- هذا يجعل الحقل يساوي نفسه
            # الأفضل تربطه بالفاتورة/السند:
            # picking.credit_note_id = rec.id  (إذا الحقل فعلاً Many2one على الفاتورة/السند)
    
            rec.create_operation = True
            # rec.vendor_return_picking_id = picking.id if "vendor_return_picking_id" in rec._fields else rec.create_operation

    def button_create_operation(self):
        for rec in self:
            if rec.move_type == 'in_refund':
                self.button_create_vendor_return()

            if rec.move_type == 'out_refund':

                if rec.create_operation == True or rec.reversal_move_id:
                    raise UserError(_("لا يمكن عمل مرتجع مرتين لنفس الفاتورة"))
                if not rec.location_id:
                    raise UserError(_("kindly set location First"))
                company = rec.partner_id.company_id | rec.location_id.company_id | rec.company_id | rec.invoice_line_ids.product_id.company_id
                if len(company) > 1:
                    raise UserError(
                        _("Multi-company conflict: Customer, Location, Invoice, or Product does not belong to the same company."))
                operation_type = self.env["stock.picking.type"].search([("code", "=", "incoming"), ("warehouse_id", "=", rec.location_id.warehouse_id.id)], limit=1)
                if not operation_type:
                    if not operation_type:
                        raise UserError(
                            _("Create an Operation Type with the warehouse of the selected location: %s.") % rec.location_id.warehouse_id.name)
                customer_location = rec.partner_id.property_stock_customer
                move_lines = []
                for line in rec.invoice_line_ids:
                    if not line.product_id:
                        continue
                
                    move_lines.append((0, 0, {
                        'name': line.product_id.name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.quantity,
                        'location_id': customer_location.id,
                        'location_dest_id': rec.location_id.id,
                        'credit_line_id': line.id,
                    }))
                opj = {
                    'partner_id': rec.partner_id.id,
                    'picking_type_id': operation_type.id,
                    'move_type': 'one',
                    'location_id': customer_location.id,
                    'location_dest_id': rec.location_id.id,
                    'origin': 'Returned - %s' % rec.name,
                    'move_ids_without_package': move_lines,
                }
                operation = self.env["stock.picking"].create(opj)
                operation.action_confirm()
                operation.credit_note_id = operation.id
                rec.create_operation = True
