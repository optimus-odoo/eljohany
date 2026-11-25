# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _get_product_free_qty_in_location(self, product, location):
        """Return free quantity in the exact source location only."""
        return product.with_context(
            location=location.id,
            compute_child=False,
        ).qty_available

    def _should_skip_free_qty_check(self, move):
        """Skip moves that should not be validated against free qty."""
        return (
            move.state in ('done', 'cancel')
            or move.scrapped
            or move.product_id.type != 'product'
        )

    def _get_demand_qty_for_validation(self, move):
        """Return requested quantity on the stock move."""
        return move.quantity or 0.0

    def _set_move_lines_qty_done(self, move, qty_to_deliver):
        """
        Distribute qty_to_deliver across move lines using qty_done.
        This is the preferred way for Odoo 17/18/19.
        """
        rounding = move.product_uom.rounding
        remaining_qty = qty_to_deliver

        move_lines = move.move_line_ids.filtered(
            lambda l: not l.result_package_id or l.product_id == move.product_id
        )

        if not move_lines:
            # fallback for rare cases where move lines are not generated yet
            move._set_quantity_done(qty_to_deliver)
            return

        for line in move_lines:
            if float_is_zero(remaining_qty, precision_rounding=rounding) or remaining_qty < 0:
                line.quantity = 0.0
                continue

            reserved_or_demand = line.quantity or 0.0

            # if line has no reserved qty, still allow assigning remaining qty carefully
            if float_is_zero(reserved_or_demand, precision_rounding=rounding):
                qty_line = remaining_qty
            else:
                qty_line = min(reserved_or_demand, remaining_qty)

            qty_line = max(0.0, qty_line)
            line.quantity = qty_line
            remaining_qty -= qty_line

        # Safety: never keep negative remainder due to float rounding
        if remaining_qty < 0:
            remaining_qty = 0.0

    def _adjust_done_qty_by__stock(self):
        """
        For outgoing pickings:
        - If demand > free qty, deliver only free qty
        - Odoo will create backorder automatically for the remaining qty
        """
        adjusted_any = False

        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue

            for move in picking.move_ids_without_package:
                if picking._should_skip_free_qty_check(move):
                    continue

                demand_qty = picking._get_demand_qty_for_validation(move)
                rounding = move.product_uom.rounding

                if float_is_zero(demand_qty, precision_rounding=rounding) or demand_qty < 0:
                    continue

                free_qty = picking._get_product_free_qty_in_location(
                    move.product_id,
                    move.location_id,
                )
                free_qty = max(0.0, free_qty)

                qty_to_deliver = min(demand_qty, free_qty)
                qty_to_deliver = max(0.0, qty_to_deliver)

                if float_compare(
                    qty_to_deliver,
                    demand_qty,
                    precision_rounding=rounding
                ) < 0:
                    adjusted_any = True

                picking._set_move_lines_qty_done(move, qty_to_deliver)

        return adjusted_any

    def _has_any_done_qty(self):
        """Check whether at least one move line has qty_done > 0."""
        for picking in self:
            for move in picking.move_ids_without_package.filtered(
                lambda m: m.state not in ('done', 'cancel')
            ):
                rounding = move.product_uom.rounding
                total_done = sum(move.move_line_ids.mapped('quantity'))
                if float_compare(total_done, 0.0, precision_rounding=rounding) > 0:
                    return True
        return False

    # ---------------------------------------------------------
    # Override validate
    # ---------------------------------------------------------
    def button_validate(self):
        bypass_group = 'group_validate_delivery_without_free_qty.delivery_validate_free_qty'

        if not self.env.user.has_group(bypass_group):
            self._adjust_done_qty_by__stock()

            # optional safety: prevent validating completely zero delivery
            if not self._has_any_done_qty():
                raise UserError(_(
                    "No available free quantity to deliver for the selected products."
                ))

        return super().button_validate()
