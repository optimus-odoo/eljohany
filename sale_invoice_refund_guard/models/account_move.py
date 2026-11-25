from odoo import _, api, models
from odoo.exceptions import AccessError
from lxml import etree

from .refund_guard_mixin import check_refunds_do_not_exceed_invoices


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        """Enable direct credit-note creation only for the dedicated group.

        The customer credit-note list is configured with ``create=0`` in the
        target database. Alter the already cached view result per request so
        the permission remains user-specific and cannot leak through Odoo's
        shared view cache.
        """
        result = super().get_view(view_id, view_type, **options)
        credit_note_view = self.env.ref(
            "account.view_out_credit_note_tree", raise_if_not_found=False
        )
        if (
            credit_note_view
            and result.get("id") == credit_note_view.id
            and view_type in ("tree", "list")
            and self.env.user.has_group(
                "sale_invoice_refund_guard.group_create_customer_refund"
            )
        ):
            arch = etree.fromstring(result["arch"])
            arch.set("create", "1")
            result["arch"] = etree.tostring(arch, encoding="unicode")
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Restrict only direct customer credit-note creation.

        A credit note linked to ``reversed_entry_id`` comes from the official
        reversal flow of a customer invoice and remains available to regular
        invoice users. The dedicated group controls only standalone/direct
        credit notes created from the Credit Notes list or through an import,
        RPC call, or custom code. Superuser operations remain available for
        migrations and system jobs.
        """
        default_move_type = self.env.context.get("default_move_type", "entry")
        creates_direct_customer_refund = any(
            vals.get("move_type", default_move_type) == "out_refund"
            and not vals.get("reversed_entry_id")
            for vals in vals_list
        )
        if (
            creates_direct_customer_refund
            and not self.env.is_superuser()
            and not self.env.user.has_group(
                "sale_invoice_refund_guard.group_create_customer_refund"
            )
        ):
            raise AccessError(
                _(
                    "غير مسموح لك بإنشاء إشعار دائن مباشر. يمكنك إنشاء المرتجع "
                    "بالطريقة الرسمية من فاتورة العميل الأصلية، أو طلب صلاحية "
                    "«إنشاء مرتجعات العملاء» للإنشاء المباشر."
                )
            )
        return super().create(vals_list)

    def action_post(self):
        refunds = self.filtered(
            lambda move: move.move_type == "out_refund"
            and move.reversed_entry_id
            and move.state == "draft"
        )
        source_ids = refunds.mapped("reversed_entry_id").ids
        if source_ids:
            # Serialize confirmation of refunds for the same invoice so two
            # users cannot consume the same remaining quantity concurrently.
            self.env.cr.execute(
                "SELECT id FROM account_move WHERE id IN %s ORDER BY id FOR UPDATE",
                [tuple(source_ids)],
            )
            check_refunds_do_not_exceed_invoices(self.env, refunds)
        return super().action_post()
