# -*- coding: utf-8 -*-
import base64
import io
import re
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError


INVOICE_MOVE_TYPES = {
    "out_invoice",
    "out_refund",
    "in_invoice",
    "in_refund",
    "out_receipt",
    "in_receipt",
}


class InvoiceAttachmentDownload(models.TransientModel):
    _name = "invoice.attachment.download"
    _description = "Temporary Invoice Attachment Download"

    file_data = fields.Binary(readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)
    invoice_count = fields.Integer(readonly=True)
    attachment_count = fields.Integer(readonly=True)

    @api.model
    def _create_download_action(self, moves):
        invoices = self._unique_invoices(moves)
        if not invoices:
            raise UserError(
                _(
                    "لم يتم العثور على فواتير ضمن السجلات المحددة.\n"
                    "No invoices were found in the selected records."
                )
            )

        archive, attachment_count = self._build_archive(invoices)
        if not attachment_count:
            raise UserError(
                _(
                    "لا توجد مرفقات قابلة للتحميل في الفواتير المحددة.\n"
                    "The selected invoices do not contain downloadable attachments."
                )
            )

        timestamp = fields.Datetime.context_timestamp(
            self, fields.Datetime.now()
        ).strftime("%Y%m%d_%H%M%S")
        wizard = self.create(
            {
                "file_data": base64.b64encode(archive),
                "file_name": "invoice_attachments_%s.zip" % timestamp,
                "invoice_count": len(invoices),
                "attachment_count": attachment_count,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=invoice.attachment.download"
                "&id=%s&field=file_data&filename_field=file_name&download=true"
                % wizard.id
            ),
            "target": "self",
        }

    @api.model
    def _unique_invoices(self, moves):
        if moves._name != "account.move":
            moves = self.env["account.move"]
        unique_ids = list(dict.fromkeys(moves.ids))
        return self.env["account.move"].browse(unique_ids).exists().filtered(
            lambda move: move.move_type in INVOICE_MOVE_TYPES
        )

    @api.model
    def _build_archive(self, invoices):
        attachments = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "in", invoices.ids),
                ("type", "in", ("binary", "url")),
            ],
            order="res_id, id",
        )
        attachments_by_invoice = {}
        for attachment in attachments:
            attachments_by_invoice.setdefault(attachment.res_id, []).append(attachment)

        output = io.BytesIO()
        attachment_count = 0
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            used_folders = set()
            for invoice in invoices.sorted(
                key=lambda move: (move.invoice_date or move.date, move.name or "", move.id)
            ):
                invoice_attachments = attachments_by_invoice.get(invoice.id, [])
                if not invoice_attachments:
                    continue

                folder = self._unique_name(
                    self._safe_name(invoice.name or "invoice_%s" % invoice.id),
                    used_folders,
                )
                used_names = set()
                for attachment in invoice_attachments:
                    name = self._safe_name(
                        attachment.name or "attachment_%s" % attachment.id
                    )
                    if attachment.type == "url":
                        if not name.lower().endswith(".url"):
                            name += ".url"
                        content = (
                            "[InternetShortcut]\r\nURL=%s\r\n" % (attachment.url or "")
                        ).encode("utf-8")
                    else:
                        content = base64.b64decode(attachment.datas or b"")

                    name = self._unique_name(name, used_names)
                    archive.writestr("%s/%s" % (folder, name), content)
                    attachment_count += 1

        return output.getvalue(), attachment_count

    @api.model
    def _safe_name(self, value):
        name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", (value or "").strip())
        name = name.strip(". ")
        return name[:180] or "unnamed"

    @api.model
    def _unique_name(self, name, used_names):
        candidate = name
        stem, dot, suffix = name.rpartition(".")
        if not dot:
            stem, suffix = name, ""
        counter = 2
        while candidate.casefold() in used_names:
            candidate = "%s (%s)%s%s" % (
                stem,
                counter,
                "." if suffix else "",
                suffix,
            )
            counter += 1
        used_names.add(candidate.casefold())
        return candidate
