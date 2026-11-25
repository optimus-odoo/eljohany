# -*- coding: utf-8 -*-

from odoo import fields, models


class VendorStockDifferenceResult(models.TransientModel):
    _name = 'vendor.stock.difference.result'
    _description = 'Vendor Stock Difference Result'
    _order = 'partner_name, product_name'

    wizard_id = fields.Many2one(
        'vendor.stock.difference.wizard',
        required=True,
        ondelete='cascade',
    )

    company_id = fields.Many2one(
        'res.company',
        required=True,
    )

    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        readonly=True,
    )

    partner_name = fields.Char(
        string='Vendor Name',
        readonly=True,
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True,
    )

    product_name = fields.Char(
        string='Product Name',
        readonly=True,
    )

    group_by = fields.Selection([
        ('supplier', 'Vendor'),
        ('supplier_product', 'Vendor + Product'),
    ], readonly=True)

    invoice_value = fields.Monetary(
        string='Vendor Bills Value',
        currency_field='currency_id',
        readonly=True,
    )

    vendor_debit = fields.Monetary(
        string='Total Debit',
        currency_field='currency_id',
        readonly=True,
    )

    vendor_credit = fields.Monetary(
        string='Total Credit',
        currency_field='currency_id',
        readonly=True,
    )

    vendor_gl_balance = fields.Monetary(
        string='Partner Ledger Balance',
        currency_field='currency_id',
        readonly=True,
    )

    stock_value = fields.Monetary(
        string='Stock Balance',
        currency_field='currency_id',
        readonly=True,
    )

    difference = fields.Monetary(
        string='Result',
        currency_field='currency_id',
        readonly=True,
    )
