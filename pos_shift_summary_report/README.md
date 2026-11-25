# POS Shift Summary Report

Arabic 80 mm POS shift report for Odoo 17.

Implementation task owner: **Ali Elsharkawy (علي الشرقاوي)**.

## Behaviour

- Managers select one company, one or more POS configurations, and exact inclusive start/end timestamps.
- Gross sales are tax-included sales before line discounts and refunds; net sales subtracts both. Taxes, cash rounding, and payment-method totals are based on valid POS orders inside the exact range.
- Cash drawer movements use the actual payment and cash-move timestamps.
- Opening and expected cash are reconstructed for partial-session ranges.
- Counted cash and the difference are displayed only when the selected range reaches the end of a closed session.
- The closing user is recorded for sessions closed after this module is installed. Historical sessions show that the closing user was not recorded.
- The PDF is a standalone Arabic RTL 80 mm layout, skips the unrelated company document-layout configurator, and does not depend on the company's external document layout.
- The closing popup contains an independent **Shift Report** button. It downloads a snapshot of the current session without closing it, changing its state, or redirecting the cashier. Closing the session does not download the report automatically.
- Both the standard daily Sales Details report and the 80 mm shift report include a global product ranking by net units after refunds (descending), with net tax-included value as the tie breaker. Sold, returned, and net quantities are shown separately, with each product's unit of measure. All prices and discounts for a product are combined in the ranking.
- The standard Sales Details report additionally shows each refund order's reference, receipt, tracking number, date/time, customer, cashier, POS, session, actual linked accounting invoice/credit note, original receipt/invoice references, payments, notes, and negative refund lines with quantity, unit price, discount, untaxed amount, tax, and tax-included amount.
- Refund-line totals remain distinct from the net total/payment of mixed sale-and-refund exchange orders. Missing invoice/original links are explicitly labelled. Period and session filters follow the standard Odoo report, including sessions crossing midnight, and no sales records are modified.
