from base64 import b64decode

from odoo import fields
from odoo.tests.common import TransactionCase


class TestAccountMoveQrCode(TransactionCase):
    def test_qr_code_payload_is_base64_encoded(self):
        vat = "310123456700003"
        self.env.company.vat = vat
        partner = self.env["res.partner"].create({"name": "QR Customer"})
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_date": fields.Date.today(),
                "l10n_sa_confirmation_datetime": fields.Datetime.now(),
            }
        )

        move._compute_qr_code_str()
        payload = b64decode(move.l10n_sa_qr_code_str, validate=True)

        self.assertEqual(payload[0], 1)
        self.assertIn(vat.encode(), payload)
