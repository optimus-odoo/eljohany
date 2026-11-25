# -*- coding: utf-8 -*-

from odoo import models, fields, api
from num2words import num2words


class Company(models.Model):
    _inherit = 'res.company'

    is_esdar = fields.Boolean()


class AccountMove(models.Model):
    _inherit = 'account.move'

    customer_vat = fields.Char(
        string='Customer VAT Number',
        related='partner_id.vat',
        readonly=True,
    )

    def amount_to_text_ar(self, amount, currency):
        integer_part = int(amount)
        decimal_part = int(round((amount - integer_part) * 100))

        main = currency.currency_unit_label or currency.name
        sub = currency.currency_subunit_label or ''

        text = num2words(integer_part, lang='ar') + f' {main}'
        if decimal_part:
            text += f' و {num2words(decimal_part, lang="ar")} {sub}'
        return text

    def action_print(self):
        esdar = self.env.company.is_esdar
        if esdar:
            return self.env.ref('invoice_prints.id_report_invoice_print_esdar').report_action(self)
        else:
            return self.env.ref('invoice_prints.id_report_invoice_print_All').report_action(self)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    stock_location_id = fields.Many2one('stock.location', string="Location")


class SalerOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_invoice_line(self, **optional_values):
        invoice_line = super()._prepare_invoice_line(**optional_values)
        invoice_line['stock_location_id'] = self.stock_location_id.id
        return invoice_line
