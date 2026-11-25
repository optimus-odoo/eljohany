from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    seq_num = fields.Integer(
        help="Shows the sequence of this line in the invoice.",
        string="Num",
        store=True,
        copy=False
    )


class AccountMove(models.Model):
    _inherit = "account.move"

    def _reset_sequence(self):
        # This part is just modifying sequences and so does not need a check
        seq = 1
        for line in self.invoice_line_ids:
            line.seq_num = seq
            seq += 1

    @api.onchange("invoice_line_ids")
    def _onchange_invoice_line_ids_line_sequence(self):
        self._reset_sequence()

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        result._reset_sequence()
        return result

    def write(self, values):
        reset_sequence = "invoice_line_ids" in values
        res = super().write(values)
        if reset_sequence:
            self._reset_sequence()
        return res


class StockMoveInh(models.Model):
    _inherit = "stock.move"

    seq_num = fields.Integer(
        help="Shows the sequence of this line in the invoice.",
        string="Num",
        store=True,
        copy=False
    )


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _reset_sequence(self):
        # This part is just modifying sequences and so does not need a check
        seq = 1
        for line in self.move_ids_without_package:
            line.seq_num = seq
            seq += 1

    @api.onchange("move_ids_without_package")
    def _onchange_move_ids_without_package_line_sequence(self):
        self._reset_sequence()

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        result._reset_sequence()
        return result

    def write(self, values):
        res = super().write(values)
        self._reset_sequence()
        return res


class AddSeqInSales(models.Model):
    _inherit = 'sale.order.line'

    num = fields.Integer()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            sequence_numbers = line.order_id.order_line.mapped('num')
            line.num = max(sequence_numbers, default=0) + 1
        return lines


class AddSeqInPurchase(models.Model):
    _inherit = 'purchase.order.line'

    num = fields.Integer()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            sequence_numbers = line.order_id.order_line.mapped('num')
            line.num = max(sequence_numbers, default=0) + 1
        return lines
