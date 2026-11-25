from odoo import Command
from odoo.addons.sale.tests.common import TestSaleCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestDeliveryInvoiceRule(TestSaleCommon):

    def _create_sale_with_delivery(self):
        product = self.env['product.product'].create({
            'name': 'Delivery Invoice Rule Test Product',
            'type': 'consu',
            'invoice_policy': 'order',
            'list_price': 100.0,
        })
        sale = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'order_line': [
                Command.create({
                    'name': product.name,
                    'product_id': product.id,
                    'product_uom_qty': 1.0,
                    'product_uom': product.uom_id.id,
                    'price_unit': product.list_price,
                }),
            ],
        })
        sale.action_confirm()
        self.assertEqual(len(sale.picking_ids), 1)
        return sale, sale.picking_ids

    def test_delivery_without_invoice_is_allowed(self):
        sale, picking = self._create_sale_with_delivery()
        self.assertFalse(sale.invoice_ids)
        self.assertFalse(picking._get_delivery_blocking_invoices())

        picking.move_ids.write({'quantity': 1.0, 'picked': True})
        picking.button_validate()

        self.assertEqual(picking.state, 'done')

    def test_draft_invoice_blocks_delivery(self):
        sale, picking = self._create_sale_with_delivery()
        invoice = sale._create_invoices()
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(picking._get_delivery_blocking_invoices(), invoice)

        with self.assertRaises(ValidationError):
            picking.button_validate()
