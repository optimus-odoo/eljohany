# Eljohany Executive Intelligence

Secure analytics foundation for Odoo 17 Community. The implementation is split
into installable providers so an unavailable business application is never a
hard dependency of the whole center.

## Modules

- `eljohany_executive_intelligence_core`: dashboard catalog, user/profile
  authorization, immutable access audit log, shared filters, and OWL interface.
- `eljohany_executive_intelligence_inventory`: warehouse scope and current stock
  quantity/replenishment indicators.
- `eljohany_executive_intelligence_purchase`: confirmed purchase value, open and
  overdue receipts, supplier lead time, supplier ranking, and monthly trend.
- `eljohany_executive_intelligence_extended`: executive, finance, sales,
  product, HR, manufacturing, operational forecast, and verified risk providers.

## Installation order

Install or upgrade `eljohany_executive_intelligence_purchase` to install the
complete provider chain, or install core/inventory separately when only those
layers are required.

Installation and every module upgrade apply an idempotent default configuration:

- the system administrator receives the center administrator role, every
  implemented dashboard, all of the administrator's companies and warehouses,
  and management actions;
- internal users in the standard Purchase role receive the Procurement dashboard;
- internal users in the standard Inventory role receive the Inventory dashboard;
- users in both roles receive both dashboards;
- accounting, sales, HR and manufacturing users receive their matching extended
  dashboards, while department managers receive the verified risk center;
- the system administrator receives all ten provider-backed dashboards;
- catalog entries without an installed executive-intelligence data provider stay
  hidden even when the corresponding standard Odoo business app is installed;
- manager roles receive drill-down and export permission;
- viewer and manager profiles are generated for every company, with that
  company's warehouses already selected.

New users and later changes to Odoo roles or allowed companies are synchronized
automatically. Existing manual profiles and custom scopes are not overwritten.
Clear **Automatic Role-Based Configuration** on a user before maintaining that
user's scope manually.

An enabled user with no configured company/dashboard scope sees no data. This is
intentional default-deny behavior. Manual configuration remains available under
**Executive Intelligence Center → Configuration** when an exception is needed.

## Data integrity rules

- Business data is queried in the current user's environment; providers do not
  use `sudo()` for purchase, stock, supplier, or product rows.
- A requested company or warehouse must be inside the configured scope.
- Existing `user_warehouse_restriction` scope is intersected when that module and
  its user group are active.
- Purchase amounts are converted per order to company currency using the order
  date. Different company currencies are displayed separately.
- Quantities with different units of measure are never added into one headline
  total.
- Large interactive purchase ranges withhold value analysis after the live-row
  limit instead of returning a partial value as if it were complete.
- Dashboard/profile metadata and access audit creation are the only intentional
  administrative `sudo()` use cases.
- Every visual payload is validated before RPC delivery. Unsupported chart
  types, non-finite values, and invalid geographic coordinates fail explicitly
  instead of reaching the browser as misleading visuals.

## Visual analytics

The shared OWL interface renders KPI comparisons, line and area trends, bars,
columns, gauges, progress indicators, heatmaps, coordinate-based geographic
distributions, and searchable/sortable detail tables without an external CDN.
Providers supply numeric source values and formatted display values separately.

- Trend counts are used when aggregating monetary values would mix currencies.
- Gauges and progress indicators state their real denominator; no synthetic
  budget or target is invented.
- Geographic charts are returned only when the commercial partner record has
  valid latitude and longitude values. Records without coordinates are omitted
  and the chart documents that limitation.
- Table filtering and sorting operate only on the rows already authorized and
  returned by the server; they never broaden company or warehouse scope.

## Verification

The module includes transaction tests for default-deny access, direct RPC denial,
company scope, immutable access logs, visual payload validation, real
purchase-order amounts, warehouse scope, and real stock quants. Run them in an
Odoo 17 test database with:

```text
--test-enable --stop-after-init \
  -i eljohany_executive_intelligence_core,eljohany_executive_intelligence_inventory,eljohany_executive_intelligence_purchase
```

