# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    last_customer_price = fields.Float(string="Last Price Used", readonly=True)

    @api.onchange("product_template_id", "order_partner_id")
    def _onchange_sale_line_last_customer_price(self):
        for rec in self:
            if not rec.order_partner_id or not rec.product_template_id:
                rec.last_customer_price = 0.0
                continue
            line = self.env["sale.order.line"].search([
                ("order_partner_id", "=", rec.order_partner_id.id),
                ("product_template_id", "=", rec.product_template_id.id),
                ("company_id", "=", rec.company_id.id),
                ("currency_id", "=", rec.currency_id.id),
                ("state", "=", "sale"),
            ], order="id desc", limit=1)
            rec.last_customer_price = line.price_unit if line else 0.0


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.onchange("partner_id")
    def _onchange_sale_partner_last_customer_price(self):
        for rec in self:
            for line in rec.order_line:
                line._onchange_sale_line_last_customer_price()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    last_customer_price = fields.Float(string="Last Price Used", readonly=True)

    @api.onchange("product_id", "partner_id")
    def _onchange_purchase_line_last_customer_price(self):
        for rec in self:
            if not rec.partner_id or not rec.product_id:
                rec.last_customer_price = 0.0
                continue
            line = self.env["purchase.order.line"].search([
                ("partner_id", "=", rec.partner_id.id),
                ("product_id", "=", rec.product_id.id),
                ("company_id", "=", rec.company_id.id),
                ("currency_id", "=", rec.currency_id.id),
                ("state", "in", ("purchase", "done")),
            ], order="id desc", limit=1)
            rec.last_customer_price = line.price_unit if line else 0.0


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.onchange("partner_id")
    def _onchange_purchase_partner_last_customer_price(self):
        for rec in self:
            for line in rec.order_line:
                line._onchange_purchase_line_last_customer_price()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    last_customer_price = fields.Monetary(
        string="Last Price Used",
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )

    def _get_last_customer_price(self):
        self.ensure_one()
        move = self.move_id
        partner = move.partner_id
        if move.move_type != "out_refund" or not partner or not self.product_id:
            return 0.0

        domain = [
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "=", "out_invoice"),
            ("move_id.partner_id", "=", partner.id),
            ("move_id.company_id", "=", move.company_id.id),
            ("move_id.currency_id", "=", move.currency_id.id),
            ("product_id", "=", self.product_id.id),
            ("display_type", "=", "product"),
        ]
        if self.product_uom_id:
            domain.append(("product_uom_id", "=", self.product_uom_id.id))

        invoice_line = self.env["account.move.line"].search(
            domain,
            order="date desc, id desc",
            limit=1,
        )
        if invoice_line:
            return invoice_line.price_unit

        # A confirmed sale can be the latest price even when it has not been
        # invoiced yet, so use it only when no posted customer invoice exists.
        sale_domain = [
            ("order_partner_id", "=", partner.id),
            ("product_id", "=", self.product_id.id),
            ("company_id", "=", move.company_id.id),
            ("currency_id", "=", move.currency_id.id),
            ("state", "=", "sale"),
        ]
        if self.product_uom_id:
            sale_domain.append(("product_uom", "=", self.product_uom_id.id))
        sale_line = self.env["sale.order.line"].search(
            sale_domain,
            order="id desc",
            limit=1,
        )
        return sale_line.price_unit if sale_line else 0.0

    @api.onchange("product_id", "product_uom_id")
    def _onchange_last_customer_price(self):
        for line in self:
            line.last_customer_price = line._get_last_customer_price()


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.onchange("partner_id", "currency_id", "company_id")
    def _onchange_invoice_lines_last_customer_price(self):
        for move in self:
            for line in move.invoice_line_ids:
                line.last_customer_price = line._get_last_customer_price()
