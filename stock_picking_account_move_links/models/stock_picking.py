# -*- coding: utf-8 -*-

from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    linked_account_move_ids = fields.Many2many(
        comodel_name="account.move",
        string="القيود المحاسبية المرتبطة",
        compute="_compute_linked_account_moves",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )
    linked_account_move_count = fields.Integer(
        string="إجمالي القيود",
        compute="_compute_linked_account_moves",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )
    valuation_account_move_count = fields.Integer(
        string="قيود التقييم المخزني",
        compute="_compute_linked_account_moves",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )
    commercial_account_move_count = fields.Integer(
        string="الفواتير والإشعارات",
        compute="_compute_linked_account_moves",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )

    def _filter_linked_account_moves(self, account_moves):
        """Keep only visible, active entries belonging to the picking company."""
        self.ensure_one()
        return account_moves.filtered(
            lambda move: move.company_id == self.company_id and move.state != "cancel"
        )

    def _get_valuation_account_moves(self):
        """Return journal entries linked through stock moves and valuation layers."""
        self.ensure_one()
        stock_moves = self.move_ids
        valuation_layers = stock_moves.stock_valuation_layer_ids
        pending_layers = valuation_layers

        # Landed costs and revaluations can create child valuation layers. Walk
        # the real layer relationship instead of guessing from references.
        while pending_layers:
            child_layers = pending_layers.stock_valuation_layer_ids - valuation_layers
            if not child_layers:
                break
            valuation_layers |= child_layers
            pending_layers = child_layers

        account_moves = valuation_layers.account_move_id | stock_moves.account_move_ids
        return self._filter_linked_account_moves(account_moves)

    def _get_sale_account_moves(self):
        """Return customer invoices/refunds linked to the picking sale lines."""
        self.ensure_one()
        invoice_moves = self.move_ids.sale_line_id.invoice_lines.move_id.filtered(
            lambda move: move.move_type in ("out_invoice", "out_refund", "out_receipt")
        )
        return self._filter_linked_account_moves(invoice_moves)

    def _get_purchase_account_moves(self):
        """Return vendor bills/refunds linked to the picking purchase lines."""
        self.ensure_one()
        invoice_moves = self.move_ids.purchase_line_id.invoice_lines.move_id.filtered(
            lambda move: move.move_type in ("in_invoice", "in_refund", "in_receipt")
        )
        return self._filter_linked_account_moves(invoice_moves)

    @api.model
    def _classify_linked_account_moves(
        self, valuation_moves, sale_moves, purchase_moves
    ):
        """Deduplicate linked entries and classify every resulting entry."""
        all_moves = valuation_moves | sale_moves | purchase_moves
        source_by_move_id = {}

        for account_move in all_moves:
            sources = []
            if account_move in valuation_moves:
                sources.append("valuation")
            if account_move in sale_moves:
                sources.append("sale")
            if account_move in purchase_moves:
                sources.append("purchase")
            source_by_move_id[account_move.id] = (
                sources[0] if len(sources) == 1 else "multiple"
            )

        return all_moves, source_by_move_id

    def _get_linked_account_move_data(self):
        """Return unique entries and a source code for each one."""
        self.ensure_one()
        valuation_moves = self._get_valuation_account_moves()
        sale_moves = self._get_sale_account_moves()
        purchase_moves = self._get_purchase_account_moves()
        all_moves, source_by_move_id = self._classify_linked_account_moves(
            valuation_moves, sale_moves, purchase_moves
        )

        return all_moves.sorted(key=lambda move: (move.date, move.id), reverse=True), {
            "valuation": valuation_moves,
            "commercial": sale_moves | purchase_moves,
            "source_by_move_id": source_by_move_id,
        }

    @api.depends(
        "move_ids.account_move_ids",
        "move_ids.stock_valuation_layer_ids.account_move_id",
        "move_ids.stock_valuation_layer_ids.stock_valuation_layer_ids.account_move_id",
        "move_ids.sale_line_id.invoice_lines.move_id",
        "move_ids.purchase_line_id.invoice_lines.move_id",
    )
    def _compute_linked_account_moves(self):
        for picking in self:
            account_moves, details = picking._get_linked_account_move_data()
            picking.linked_account_move_ids = account_moves
            picking.linked_account_move_count = len(account_moves)
            picking.valuation_account_move_count = len(details["valuation"])
            picking.commercial_account_move_count = len(details["commercial"])
