from collections import defaultdict

from odoo import _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


def _is_quantity_controlled_line(line):
    """Keep real sale items and ignore negative financial adjustment lines.

    Percentage discounts stay on their positive product line and therefore
    remain quantity-controlled.  A separate negative discount product is a
    monetary adjustment, not a returnable unit, and must not consume quantity.
    """
    return (
        line.display_type == "product"
        and line.product_id
        and line.price_subtotal >= 0.0
    )


def _product_quantities(lines):
    quantities = defaultdict(float)
    for line in lines.filtered(_is_quantity_controlled_line):
        product = line.product_id
        quantities[product.id] += line.product_uom_id._compute_quantity(
            abs(line.quantity), product.uom_id
        )
    return quantities


def _exceeded_product_quantities(env, invoiced, refunded, product_ids):
    """Return exceeded quantities only for products in the current refund."""
    exceeded = []
    for product_id in product_ids:
        product = env["product.product"].browse(product_id)
        invoiced_quantity = invoiced.get(product_id, 0.0)
        refunded_quantity = refunded.get(product_id, 0.0)
        if float_compare(
            refunded_quantity,
            invoiced_quantity,
            precision_rounding=product.uom_id.rounding,
        ) > 0:
            exceeded.append((product, refunded_quantity, invoiced_quantity))
    return exceeded


def check_refunds_do_not_exceed_invoices(env, refunds_to_post):
    """Validate only when refund drafts are being posted.

    Existing drafts do not reserve quantities. Previously posted refunds plus
    all refunds in the current posting batch are compared with the source
    invoice, which lets users create and edit a second partial refund first.
    Historical excesses for products absent from the current posting batch do
    not block an otherwise valid refund.
    """
    refunds_to_post = refunds_to_post.filtered(
        lambda move: move.move_type == "out_refund" and move.reversed_entry_id
    )
    for invoice in refunds_to_post.mapped("reversed_entry_id"):
        current_refunds = refunds_to_post.filtered(
            lambda refund: refund.reversed_entry_id == invoice
        )
        posted_refunds = env["account.move"].search([
            ("move_type", "=", "out_refund"),
            ("reversed_entry_id", "=", invoice.id),
            ("state", "=", "posted"),
        ])
        invoiced = _product_quantities(invoice.invoice_line_ids)
        current = _product_quantities(current_refunds.invoice_line_ids)
        refunded = _product_quantities(
            (posted_refunds | current_refunds).invoice_line_ids
        )
        exceeded_quantities = _exceeded_product_quantities(
            env,
            invoiced,
            refunded,
            current,
        )
        exceeded = [
            "- %s: %s / %s %s"
            % (
                product.display_name,
                refunded_quantity,
                invoiced_quantity,
                product.uom_id.display_name,
            )
            for product, refunded_quantity, invoiced_quantity in exceeded_quantities
        ]
        if exceeded:
            raise UserError(
                _(
                    "لا يمكن تأكيد المرتجع لأن إجمالي الكمية المرتجعة يتجاوز "
                    "كمية الفاتورة %(invoice)s:\n%(details)s\n\n"
                    "عدّل كميات المرتجع الحالي إلى الكميات المتبقية ثم أعد التأكيد.",
                    invoice=invoice.display_name,
                    details="\n".join(exceeded),
                )
            )
