# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_download_invoice_attachments(self):
        return self.env["invoice.attachment.download"]._create_download_action(self)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def action_download_invoice_attachments(self):
        return self.env["invoice.attachment.download"]._create_download_action(
            self.mapped("move_id")
        )
