# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    stock_picking_link_source = fields.Selection(
        selection=[
            ("valuation", "تقييم مخزني"),
            ("sale", "فاتورة أو إشعار عميل"),
            ("purchase", "فاتورة أو إشعار مورد"),
            ("multiple", "متعدد المصادر"),
        ],
        string="مصدر الارتباط",
        compute="_compute_stock_picking_link_source",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )
    stock_picking_debit_total = fields.Monetary(
        string="إجمالي المدين",
        currency_field="company_currency_id",
        compute="_compute_stock_picking_entry_totals",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )
    stock_picking_credit_total = fields.Monetary(
        string="إجمالي الدائن",
        currency_field="company_currency_id",
        compute="_compute_stock_picking_entry_totals",
        compute_sudo=False,
        groups="account.group_account_readonly",
    )

    @api.depends_context("stock_picking_link_id")
    def _compute_stock_picking_link_source(self):
        source_by_move_id = {}
        picking_id = self.env.context.get("stock_picking_link_id")
        if picking_id:
            picking = self.env["stock.picking"].browse(picking_id).exists()
            if picking:
                _account_moves, details = picking._get_linked_account_move_data()
                source_by_move_id = details["source_by_move_id"]

        for account_move in self:
            account_move.stock_picking_link_source = source_by_move_id.get(
                account_move.id, False
            )

    @api.depends("line_ids.debit", "line_ids.credit")
    def _compute_stock_picking_entry_totals(self):
        for account_move in self:
            account_move.stock_picking_debit_total = sum(account_move.line_ids.mapped("debit"))
            account_move.stock_picking_credit_total = sum(
                account_move.line_ids.mapped("credit")
            )

    def action_open_from_stock_picking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
