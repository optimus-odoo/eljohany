# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProductTemplateInh(models.Model):
    _inherit = 'product.template'

    last_so_for_product_id = fields.Many2one(comodel_name="sale.order", copy=False)
    last_so_price = fields.Float(copy=False)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    last_so_price = fields.Float(copy=False, readonly=True)
    last_so_for_product_id = fields.Many2one(comodel_name="sale.order", copy=False, readonly=True)

    @api.onchange("product_template_id")
    def get_last_product_data(self):
        for rec in self:
            rec.last_so_price = rec.product_template_id.last_so_price
            rec.last_so_for_product_id = rec.product_template_id.last_so_for_product_id.id


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for line in self.order_line:
            line.product_template_id.last_so_price = line.price_unit
            line.product_template_id.last_so_for_product_id = line.order_id.id
        return res


class ProductProduct(models.Model):
    _inherit = 'product.product'

    last_po_for_product_id = fields.Many2one(comodel_name="purchase.order", copy=False)
    last_po_price = fields.Float(copy=False)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    last_po_for_product_id = fields.Many2one(comodel_name="purchase.order", copy=False, readonly=True)
    last_po_price = fields.Float(copy=False, readonly=True)

    @api.onchange("product_id")
    def get_last_product_data(self):
        for rec in self:
            rec.last_po_price = rec.product_id.last_po_price
            rec.last_po_for_product_id = rec.product_id.last_po_for_product_id.id


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    state = fields.Selection(
        selection_add=[
            ('waiting_manager_approve', 'Waiting Manager Approve'),
            ('to approve',),
        ],
        ondelete={'waiting_manager_approve': 'set default'},
    )

    def button_confirm(self):
        for order in self:
            order.order_line._validate_analytic_distribution()
            order._add_supplier_to_product()
            # Deal with double validation process
            if order._approval_allowed():
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
            for line in order.order_line:
                line.product_id.last_po_price = line.price_unit
                line.product_id.last_po_for_product_id = line.order_id.id
        return True

    def action_submit_to_manager(self):
        for rec in self:
            rec.state = "waiting_manager_approve"


    def button_confirm_all_orders(self):
        for order in self:
            if order.state == 'waiting_manager_approve':
                order.button_confirm()
            else:
                raise ValidationError(_("You can only confirm orders that are in 'Waiting Manager Approve' state."))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    lock_lines = fields.Boolean()
    max_qty = fields.Float()

    @api.onchange("quantity")
    def check_max_qty_limit(self):
        for rec in self:
            if rec.quantity > rec.max_qty and rec.lock_lines:
                raise UserError(_("The requested quantity - %s exceeds the allowed quantity - %s  for Product %s.") % (
                    rec.quantity, rec.max_qty, rec.name))


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def reverse_moves(self, is_modify=False):
        self.ensure_one()
        moves = self.move_ids

        # Create default values.
        partners = moves.company_id.partner_id + moves.commercial_partner_id

        bank_ids = self.env['res.partner.bank'].search([
            ('partner_id', 'in', partners.ids),
            ('company_id', 'in', moves.company_id.ids + [False]),
        ], order='sequence DESC')
        partner_to_bank = {bank.partner_id: bank for bank in bank_ids}
        default_values_list = []
        for move in moves:
            if move.is_outbound():
                partner = move.company_id.partner_id
            else:
                partner = move.commercial_partner_id
            default_values_list.append({
                'partner_bank_id': partner_to_bank.get(partner, self.env['res.partner.bank']).id,
                **self._prepare_default_reversal(move),
            })

        batches = [
            [self.env['account.move'], [], True],  # Moves to be cancelled by the reverses.
            [self.env['account.move'], [], False],  # Others.
        ]
        for move, default_vals in zip(moves, default_values_list):
            is_auto_post = default_vals.get('auto_post') != 'no'
            is_cancel_needed = not is_auto_post and (is_modify or self.move_type == 'entry')
            batch_index = 0 if is_cancel_needed else 1
            batches[batch_index][0] |= move
            batches[batch_index][1].append(default_vals)

        # Handle reverse method.
        moves_to_redirect = self.env['account.move']
        for moves, default_values_list, is_cancel_needed in batches:
            new_moves = moves._reverse_moves(default_values_list, cancel=is_cancel_needed)
            moves._message_log_batch(
                bodies={move.id: _('This entry has been %s', reverse._get_html_link(title=_("reversed"))) for
                        move, reverse in zip(moves, new_moves)}
            )

            if is_modify:
                moves_vals_list = []
                for move in moves.with_context(include_business_fields=True):
                    data = move.copy_data(self._modify_default_reverse_values(move))[0]
                    data['line_ids'] = [line for line in data['line_ids'] if
                                        line[2]['display_type'] in ('product', 'line_section', 'line_note')]
                    moves_vals_list.append(data)
                new_moves = self.env['account.move'].create(moves_vals_list)
            moves_to_redirect |= new_moves
            for line in new_moves.invoice_line_ids:
                line.lock_lines = True
                line.max_qty = line.quantity

        self.new_move_ids = moves_to_redirect

        # Create action.
        action = {
            'name': _('Reverse Moves'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
        }
        if len(moves_to_redirect) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': moves_to_redirect.id,
                'context': {'default_move_type': moves_to_redirect.move_type},
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', moves_to_redirect.ids)],
            })
            if len(set(moves_to_redirect.mapped('move_type'))) == 1:
                action['context'] = {'default_move_type': moves_to_redirect.mapped('move_type').pop()}
        return action
