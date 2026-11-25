# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VendorStockDifferenceWizard(models.TransientModel):
    _name = 'vendor.stock.difference.wizard'
    _description = 'Vendor Stock Difference Wizard'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )

    partner_ids = fields.Many2many(
        'res.partner',
        string='Vendors',
        domain=[('supplier_rank', '>', 0)],
    )

    product_ids = fields.Many2many(
        'product.product',
        string='Products',
    )

    group_by = fields.Selection([
        ('supplier', 'Vendor'),
        ('supplier_product', 'Vendor + Product'),
    ], required=True, default='supplier')

    result_line_ids = fields.One2many(
        'vendor.stock.difference.result',
        'wizard_id',
        string='Results',
    )

    notes = fields.Text(
        readonly=True,
        default=(
            "Vendor Balance is calculated like the Partner Ledger balance from posted "
            "journal items on trade payable/receivable accounts up to the end date, "
            "including the initial balance before the start date. "
            "Vendor Balance = Debit - Credit. "
            "Difference = Stock Value + Vendor Balance. "
            "Stock value is linked to vendor through the related purchase line on stock moves."
        ),
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_to < wizard.date_from:
                raise ValidationError(
                    _('End Date must be greater than or equal to Start Date.')
                )

    def _get_default_grouped_dict(self):
        return defaultdict(lambda: {
            'invoice_value': 0.0,
            'vendor_debit': 0.0,
            'vendor_credit': 0.0,
            'vendor_gl_balance': 0.0,
            'stock_value': 0.0,
        })

    def _get_invoice_data(self):
        """
        Vendor bill product lines value.
        This is not the GL balance.
        It is only for reference/comparison by product.
        """
        self.ensure_one()

        aml_domain = [
            ('move_id.state', '=', 'posted'),
            ('move_id.move_type', '=', 'in_invoice'),
            ('move_id.invoice_date', '>=', self.date_from),
            ('move_id.invoice_date', '<=', self.date_to),
            ('move_id.company_id', '=', self.company_id.id),
            ('product_id', '!=', False),
        ]

        if self.partner_ids:
            aml_domain.append(('move_id.partner_id', 'in', self.partner_ids.ids))

        if self.product_ids:
            aml_domain.append(('product_id', 'in', self.product_ids.ids))

        lines = self.env['account.move.line'].search(aml_domain)
        grouped = self._get_default_grouped_dict()

        for line in lines:
            partner = line.move_id.partner_id
            product = line.product_id

            key = (
                partner.id,
                product.id if self.group_by == 'supplier_product' else False,
            )

            grouped[key]['invoice_value'] += line.price_subtotal

        return grouped

    def _get_vendor_gl_balance_data(self, grouped):
        """
        Actual vendor balance from Partner Ledger up to the selected end date.

        In Odoo:
            balance = debit - credit

        Partner Ledger shows vendor/payable balances using this same sign, so a
        payable balance is usually negative and an advance/debit balance is positive.
        The lower date bound is intentionally not applied here because the partner
        ledger balance includes the initial balance before date_from.
        """
        self.ensure_one()

        aml_domain = [
            ('move_id.state', '=', 'posted'),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('partner_id', '!=', False),
            ('account_id.account_type', 'in', ('liability_payable', 'asset_receivable')),
            ('account_id.non_trade', '=', False),
        ]

        if self.partner_ids:
            aml_domain.append(('partner_id', 'in', self.partner_ids.ids))

        rows = self.env['account.move.line'].read_group(
            domain=aml_domain,
            fields=['debit:sum', 'credit:sum'],
            groupby=['partner_id'],
            lazy=False,
        )

        for row in rows:
            partner_id = row['partner_id'][0]
            partner = self.env['res.partner'].browse(partner_id)

            vendor_debit = row.get('debit', 0.0)
            vendor_credit = row.get('credit', 0.0)
            vendor_gl_balance = vendor_debit - vendor_credit

            key = (partner.id, False)
            grouped[key]['vendor_debit'] += vendor_debit
            grouped[key]['vendor_credit'] += vendor_credit
            grouped[key]['vendor_gl_balance'] += vendor_gl_balance

        return grouped

    def _get_stock_data(self, grouped):
        """
        Stock value from valuation layers.

        Vendor is detected from:
            stock.valuation.layer.stock_move_id.purchase_line_id.order_id.partner_id

        Notes:
        - SVL without purchase linkage will be ignored.
        - Positive quantity only means receipt/increase.
        """
        self.ensure_one()

        date_from_dt = fields.Datetime.to_datetime(self.date_from)
        date_to_dt = fields.Datetime.to_datetime('%s 23:59:59' % self.date_to)

        svl_domain = [
            ('company_id', '=', self.company_id.id),
            ('create_date', '>=', date_from_dt),
            ('create_date', '<=', date_to_dt),
            ('product_id', '!=', False),
            ('stock_move_id', '!=', False),
            ('quantity', '>', 0),
        ]

        if self.product_ids:
            svl_domain.append(('product_id', 'in', self.product_ids.ids))

        valuation_layers = self.env['stock.valuation.layer'].search(svl_domain)

        for svl in valuation_layers:
            move = svl.stock_move_id
            purchase_line = move.purchase_line_id

            if not purchase_line or not purchase_line.order_id.partner_id:
                continue

            partner = purchase_line.order_id.partner_id

            if self.partner_ids and partner not in self.partner_ids:
                continue

            product = svl.product_id

            key = (
                partner.id,
                product.id if self.group_by == 'supplier_product' else False,
            )

            grouped[key]['stock_value'] += svl.value

        return grouped

    def _prepare_result_vals(self, grouped):
        self.ensure_one()

        partner_ids = {key[0] for key in grouped.keys() if key[0]}
        product_ids = {key[1] for key in grouped.keys() if key[1]}

        partners = {
            partner.id: partner
            for partner in self.env['res.partner'].browse(list(partner_ids))
        }

        products = {
            product.id: product
            for product in self.env['product.product'].browse(list(product_ids))
        }

        vals_list = []

        for (partner_id, product_id), amounts in grouped.items():
            partner = partners.get(partner_id)
            product = products.get(product_id) if product_id else False

            invoice_value = amounts.get('invoice_value', 0.0)
            vendor_debit = amounts.get('vendor_debit', 0.0)
            vendor_credit = amounts.get('vendor_credit', 0.0)
            vendor_gl_balance = amounts.get('vendor_gl_balance', 0.0)
            stock_value = amounts.get('stock_value', 0.0)

            vals_list.append({
                'wizard_id': self.id,
                'company_id': self.company_id.id,
                'partner_id': partner_id,
                'partner_name': partner.display_name if partner else '',
                'product_id': product_id or False,
                'product_name': product.display_name if product else '',
                'invoice_value': invoice_value,
                'vendor_debit': vendor_debit,
                'vendor_credit': vendor_credit,
                'vendor_gl_balance': vendor_gl_balance,
                'stock_value': stock_value,
                'difference': stock_value + vendor_gl_balance,
                'group_by': self.group_by,
            })

        return vals_list

    def action_generate(self):
        self.ensure_one()
        self.result_line_ids.unlink()

        grouped = self._get_invoice_data()
        grouped = self._get_stock_data(grouped)
        grouped = self._get_vendor_gl_balance_data(grouped)

        vals_list = self._prepare_result_vals(grouped)

        if vals_list:
            self.env['vendor.stock.difference.result'].create(vals_list)

        action = self.env.ref(
            'vendor_stock_difference_report.action_vendor_stock_difference_result'
        ).read()[0]

        action['domain'] = [('wizard_id', '=', self.id)]
        action['context'] = {
            'search_default_group_partner': 1,
            'default_wizard_id': self.id,
        }

        return action

    def action_print_pdf(self):
        self.ensure_one()

        if not self.result_line_ids:
            self.action_generate()

        return self.env.ref(
            'vendor_stock_difference_report.action_report_vendor_stock_difference'
        ).report_action(self)
