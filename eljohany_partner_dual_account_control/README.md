# Eljohany Partner Dual Account Control

This Odoo 17 module keeps one commercial partner when the same entity is both
a customer and a vendor, while enforcing two independent settlement paths:

- customer invoices, customer refunds, and customer payments use the partner's
  company-specific receivable account;
- vendor bills, vendor refunds, and vendor payments use the partner's
  company-specific payable account.

The module does not create duplicate partners or rewrite posted journal items.
It validates draft documents before and after the standard posting chain, shows
the expected settlement account and validation state on invoices and payments,
and provides an Accounting Manager audit wizard under
**Accounting > Configuration > Partner Account Audit**.

Enforcement is disabled by default for a safe rollout. Run the audit first,
correct the reported partner accounts, then enable **Customer and Vendor Account
Separation** for each company from Accounting settings.

## Important scope

The control applies only to receivable/payable settlement journal items. Product
income, expense, stock, and tax accounts remain governed by Odoo's product,
category, tax, and fiscal-position configuration.
