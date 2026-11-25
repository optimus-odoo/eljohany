# POS Required Order Type and Receipt

Implementation task owner: **Ali Elsharkawy (علي الشرقاوي)**.

This module provides the required dine-in/take-away choice and the branded,
bilingual POS receipt.

The POS order-management screen also displays a separate **Print Receipt**
button for the selected active order. It uses Odoo's standard receipt printer
with the selected order and does not load, pay, delete, or otherwise change
the order.

The order-management screen does not expose the delete/trash action for
pending cashier orders. This is enforced for desktop and mobile layouts by
the shared Ticket Screen visibility rule; it does not delete or alter any
existing order.
