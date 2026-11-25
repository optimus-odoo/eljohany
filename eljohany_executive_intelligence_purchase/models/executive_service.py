from collections import defaultdict
from datetime import datetime, time, timedelta
from statistics import mean, median

from odoo import _, fields, models


class ExecutiveIntelligenceService(models.AbstractModel):
    _inherit = "executive.intelligence.service"

    _PURCHASE_LIVE_ROW_LIMIT = 20000
    _LEAD_TIME_LIVE_ROW_LIMIT = 10000

    def _ei_supported_dashboard_codes(self):
        return super()._ei_supported_dashboard_codes() | {"purchase"}

    def _ei_get_dashboard_data(self, dashboard_code, filters, access):
        if dashboard_code == "purchase":
            return self._ei_purchase_dashboard(filters)
        return super()._ei_get_dashboard_data(dashboard_code, filters, access)

    def _ei_purchase_dashboard(self, filters):
        warehouse_ids = filters.get("warehouse_ids", [])
        if not warehouse_ids:
            return self._ei_no_warehouse_payload()

        PurchaseOrder = self.env["purchase.order"]
        StockPicking = self.env["stock.picking"]
        PurchaseOrder.check_access_rights("read")
        StockPicking.check_access_rights("read")

        start_dt = datetime.combine(filters["date_from"], time.min)
        end_dt = datetime.combine(filters["date_to"] + timedelta(days=1), time.min)
        order_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("picking_type_id.warehouse_id", "in", warehouse_ids),
            ("state", "in", ("purchase", "done")),
            ("date_order", ">=", fields.Datetime.to_string(start_dt)),
            ("date_order", "<", fields.Datetime.to_string(end_dt)),
        ]
        order_count = PurchaseOrder.search_count(order_domain)
        period_length = end_dt - start_dt
        previous_order_count = PurchaseOrder.search_count(
            [
                ("company_id", "in", filters["company_ids"]),
                ("picking_type_id.warehouse_id", "in", warehouse_ids),
                ("state", "in", ("purchase", "done")),
                (
                    "date_order",
                    ">=",
                    fields.Datetime.to_string(start_dt - period_length),
                ),
                ("date_order", "<", fields.Datetime.to_string(start_dt)),
            ]
        )

        open_receipt_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("picking_type_id.warehouse_id", "in", warehouse_ids),
            ("picking_type_id.code", "=", "incoming"),
            ("purchase_id", "!=", False),
            ("state", "not in", ("done", "cancel")),
        ]
        # stock.picking.purchase_id is a non-stored related field in Odoo 17. It
        # cannot be used as a SQL read_group key. purchase.order.receipt_status
        # is stored and represents the order-level receipt state, so it gives an
        # exact distinct order count without loading receipt records in Python.
        open_order_count = PurchaseOrder.search_count(
            [
                ("company_id", "in", filters["company_ids"]),
                ("state", "in", ("purchase", "done")),
                ("picking_type_id.warehouse_id", "in", warehouse_ids),
                ("receipt_status", "in", ("pending", "partial")),
            ]
        )
        overdue_receipt_count = StockPicking.search_count(
            open_receipt_domain
            + [("scheduled_date", "<", fields.Datetime.to_string(fields.Datetime.now()))]
        )
        open_receipt_count = StockPicking.search_count(open_receipt_domain)

        cards = [
            {
                "key": "confirmed_order_count",
                "label": _("Confirmed purchase orders"),
                "value": order_count,
                "display_value": f"{order_count:,}",
                "note": _("Orders confirmed in the selected period"),
                "comparison": self._ei_period_comparison(
                    order_count, previous_order_count
                ),
            },
            {
                "key": "open_purchase_orders",
                "label": _("Orders awaiting receipt"),
                "value": open_order_count,
                "display_value": f"{open_order_count:,}",
                "note": _("Current open incoming receipts"),
            },
            {
                "key": "overdue_receipts",
                "label": _("Overdue receipts"),
                "value": overdue_receipt_count,
                "display_value": f"{overdue_receipt_count:,}",
                "note": _("Open receipts past their scheduled date"),
            },
        ]

        orders = PurchaseOrder.search(
            order_domain,
            order="date_order, id",
            limit=self._PURCHASE_LIVE_ROW_LIMIT + 1,
        )
        if len(orders) > self._PURCHASE_LIVE_ROW_LIMIT:
            return {
                "status": "requires_precalculation",
                "message": _(
                    "The selected period contains too many orders for a live value "
                    "calculation. Counts remain exact; value analysis is withheld "
                    "until the scheduled summary is available."
                ),
                "cards": cards,
                "charts": [],
                "tables": [],
                "quality": {
                    "order_count": order_count,
                    "live_row_limit": self._PURCHASE_LIVE_ROW_LIMIT,
                },
            }

        value_by_currency = defaultdict(float)
        supplier_totals = defaultdict(lambda: {"value": 0.0, "orders": 0})
        monthly_totals = defaultdict(float)
        monthly_order_counts = defaultdict(int)
        for order in orders:
            company_currency = order.company_id.currency_id
            conversion_date = fields.Date.to_date(order.date_order)
            company_value = order.currency_id._convert(
                order.amount_untaxed,
                company_currency,
                order.company_id,
                conversion_date,
            )
            currency_key = (company_currency.id, company_currency.name)
            value_by_currency[currency_key] += company_value
            partner = order.partner_id.commercial_partner_id
            supplier_key = (
                partner.id,
                partner.display_name,
                order.company_id.id,
                order.company_id.name,
                company_currency.name,
            )
            supplier_totals[supplier_key]["value"] += company_value
            supplier_totals[supplier_key]["orders"] += 1
            month_key = fields.Date.to_string(conversion_date)[:7]
            monthly_totals[(month_key, company_currency.name)] += company_value
            monthly_order_counts[month_key] += 1

        for (currency_id, currency_name), amount in sorted(value_by_currency.items()):
            cards.append(
                {
                    "key": f"confirmed_value_{currency_id}",
                    "label": _("Confirmed purchase value (%s)") % currency_name,
                    "value": amount,
                    "display_value": f"{amount:,.2f} {currency_name}",
                    "note": _("Untaxed value converted on each order date"),
                }
            )

        lead_time_card, lead_time_quality = self._ei_purchase_lead_time_card(
            filters, warehouse_ids
        )
        if lead_time_card:
            cards.append(lead_time_card)

        supplier_rows = []
        sorted_suppliers = sorted(
            supplier_totals.items(),
            key=lambda item: item[1]["value"],
            reverse=True,
        )[:10]
        for supplier_key, totals in sorted_suppliers:
            partner_id, supplier, company_id, company, currency = supplier_key
            supplier_rows.append(
                {
                    "key": f"{partner_id}-{company_id}",
                    "supplier": supplier,
                    "company": company,
                    "orders": f"{totals['orders']:,}",
                    "value": f"{totals['value']:,.2f} {currency}",
                }
            )

        trend_rows = [
            {
                "key": f"{month}-{currency}",
                "month": month,
                "currency": currency,
                "value": f"{amount:,.2f}",
            }
            for (month, currency), amount in sorted(monthly_totals.items())
        ]
        return {
            "cards": cards,
            "charts": [
                {
                    "key": "monthly_purchase_order_trend",
                    "type": "line",
                    "title": _("Monthly confirmed purchase order trend"),
                    "subtitle": _("Confirmed order count without mixing currencies"),
                    "items": [
                        {
                            "key": month,
                            "label": month,
                            "value": count,
                            "display_value": f"{count:,}",
                        }
                        for month, count in sorted(monthly_order_counts.items())
                    ],
                },
                {
                    "key": "supplier_order_volume",
                    "type": "bar",
                    "title": _("Top suppliers by confirmed order count"),
                    "items": [
                        {
                            "key": f"{supplier_key[0]}-{supplier_key[2]}",
                            "label": supplier_key[1],
                            "value": totals["orders"],
                            "display_value": f"{totals['orders']:,}",
                        }
                        for supplier_key, totals in sorted_suppliers
                    ],
                },
                {
                    "key": "overdue_receipt_share",
                    "type": "gauge",
                    "title": _("Overdue share of open receipts"),
                    "items": [
                        {
                            "key": "overdue_receipts",
                            "label": _("Overdue receipts"),
                            "value": overdue_receipt_count,
                            "target": open_receipt_count,
                            "percent": (
                                overdue_receipt_count / open_receipt_count * 100
                                if open_receipt_count
                                else 0.0
                            ),
                            "display_value": (
                                f"{overdue_receipt_count:,} / {open_receipt_count:,}"
                            ),
                            "color": "#e84450",
                        }
                    ],
                },
            ],
            "tables": [
                {
                    "key": "top_suppliers",
                    "title": _("Top suppliers by confirmed untaxed value"),
                    "columns": [
                        {"key": "supplier", "label": _("Supplier")},
                        {"key": "company", "label": _("Company")},
                        {"key": "orders", "label": _("Orders")},
                        {"key": "value", "label": _("Value")},
                    ],
                    "rows": supplier_rows,
                },
                {
                    "key": "monthly_trend",
                    "title": _("Monthly confirmed purchase trend"),
                    "columns": [
                        {"key": "month", "label": _("Month")},
                        {"key": "currency", "label": _("Company Currency")},
                        {"key": "value", "label": _("Untaxed Value")},
                    ],
                    "rows": trend_rows,
                },
            ],
            "definitions": {
                "confirmed_value": _(
                    "Untaxed value of purchase orders in Purchase or Done state, "
                    "converted to company currency using the order date."
                ),
                "overdue_receipts": _(
                    "Open incoming receipts linked to purchase orders whose scheduled "
                    "date is before the current server time."
                ),
            },
            "quality": {
                "order_count": order_count,
                **lead_time_quality,
            },
        }

    def _ei_purchase_lead_time_card(self, filters, warehouse_ids):
        end_dt = datetime.combine(filters["date_to"] + timedelta(days=1), time.min)
        start_dt = datetime.combine(filters["date_from"], time.min)
        domain = [
            ("company_id", "in", filters["company_ids"]),
            ("picking_type_id.warehouse_id", "in", warehouse_ids),
            ("picking_type_id.code", "=", "incoming"),
            ("purchase_id", "!=", False),
            ("state", "=", "done"),
            ("date_done", ">=", fields.Datetime.to_string(start_dt)),
            ("date_done", "<", fields.Datetime.to_string(end_dt)),
        ]
        pickings = self.env["stock.picking"].search(
            domain,
            order="date_done, id",
            limit=self._LEAD_TIME_LIVE_ROW_LIMIT + 1,
        )
        if len(pickings) > self._LEAD_TIME_LIVE_ROW_LIMIT:
            return False, {"lead_time_status": "requires_precalculation"}

        lead_times = []
        anomalies = 0
        for picking in pickings:
            start = picking.purchase_id.date_approve or picking.purchase_id.date_order
            if not start or not picking.date_done:
                anomalies += 1
                continue
            days = (picking.date_done - start).total_seconds() / 86400
            if days < 0:
                anomalies += 1
                continue
            lead_times.append(days)
        if not lead_times:
            return False, {
                "lead_time_status": "no_valid_receipts",
                "lead_time_anomalies": anomalies,
            }
        average_days = mean(lead_times)
        median_days = median(lead_times)
        return (
            {
                "key": "supplier_lead_time",
                "label": _("Receipt lead time"),
                "value": average_days,
                "display_value": _("%.1f days") % average_days,
                "note": _("Median %.1f days from approval to completed receipt")
                % median_days,
            },
            {
                "lead_time_status": "ok",
                "lead_time_sample": len(lead_times),
                "lead_time_anomalies": anomalies,
            },
        )

