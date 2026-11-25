# POS Sales and Margin Report

Implementation task owner: **Ali Elsharkawy (علي الشرقاوي)**.

The report is available to Point of Sale managers under **Point of Sale > Reporting**.
It accepts one or more POS configurations and an inclusive local date-and-time range,
and exports both Excel and PDF. Odoo stores the selected timestamps in UTC; the filters
use those exact timestamps while the exported period is displayed in the user's local
timezone.

Excel and PDF exports are always rendered in Arabic and right-to-left, regardless
of the exporting user's interface language.

## Amount definitions

- **Gross Total:** quantity multiplied by the POS unit price before the line discount, excluding tax.
- **Discounts:** the POS line discount amount, excluding tax.
- **Total After Discounts:** gross total less discounts, excluding tax.
- **Tax:** grand total less total after discounts.
- **Grand Total:** total including tax.
- **Profit Margin Amount:** total after discounts less the POS line's stored total cost.
- **Profit Margin Percentage:** profit margin amount divided by total after discounts.

Paid, posted, and invoiced orders are included. Draft and cancelled orders are excluded.
Sales and refunds are netted naturally through their signed POS quantities and amounts.
All monetary amounts are converted to the selected company currency. Sales measures use
Odoo's standard POS analysis view; margin conversion also uses each order's stored POS
currency rate.

If one or more selected order lines still have uncomputed costs, the output displays a
warning because the margin can change after the related POS session is closed.
