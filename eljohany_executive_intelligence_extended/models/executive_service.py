from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, fields, models


class ExecutiveIntelligenceService(models.AbstractModel):
    _inherit = "executive.intelligence.service"

    _LIVE_ROW_LIMIT = 20000
    _DETAIL_LIMIT = 100

    def _ei_supported_dashboard_codes(self):
        return super()._ei_supported_dashboard_codes() | {
            "executive",
            "finance",
            "sales",
            "product",
            "forecast",
            "hr",
            "operations",
            "risk",
        }

    def _ei_get_dashboard_data(self, dashboard_code, filters, access):
        providers = {
            "executive": self._ei_executive_dashboard,
            "finance": self._ei_finance_dashboard,
            "sales": self._ei_sales_dashboard,
            "product": self._ei_product_dashboard,
            "forecast": self._ei_forecast_dashboard,
            "hr": self._ei_hr_dashboard,
            "operations": self._ei_operations_dashboard,
            "risk": self._ei_risk_dashboard,
        }
        provider = providers.get(dashboard_code)
        if provider:
            if dashboard_code in {"product", "forecast"} and not filters.get(
                "warehouse_ids"
            ):
                return self._ei_no_warehouse_payload()
            return provider(filters)
        return super()._ei_get_dashboard_data(dashboard_code, filters, access)

    def _ei_can_read(self, model_name):
        return self.env[model_name].check_access_rights(
            "read", raise_exception=False
        )

    def _ei_sum(self, model, domain, field_name):
        groups = model.read_group(
            domain,
            [f"{field_name}:sum"],
            [],
            lazy=False,
        )
        return groups[0].get(field_name, 0.0) if groups else 0.0

    def _ei_period_datetimes(self, filters):
        return (
            datetime.combine(filters["date_from"], time.min),
            datetime.combine(filters["date_to"] + timedelta(days=1), time.min),
        )

    def _ei_company_currency_rows(self, values):
        companies = {
            company.id: company
            for company in self.env["res.company"].browse(
                sorted(values)
            ).exists()
        }
        return companies

    def _ei_finance_dashboard(self, filters):
        MoveLine = self.env["account.move.line"]
        MoveLine.check_access_rights("read")
        start_date = fields.Date.to_string(filters["date_from"])
        end_date = fields.Date.to_string(filters["date_to"])
        expense_types = (
            "expense",
            "expense_depreciation",
            "expense_direct_cost",
        )
        income_types = ("income", "income_other")
        cards = []
        rows = []
        margin_items = []
        expense_ratio_items = []
        for company in self.env["res.company"].browse(filters["company_ids"]).exists():
            period_domain = [
                ("company_id", "=", company.id),
                ("move_id.state", "=", "posted"),
                ("date", ">=", start_date),
                ("date", "<=", end_date),
            ]
            revenue = -self._ei_sum(
                MoveLine,
                period_domain + [("account_id.account_type", "in", income_types)],
                "balance",
            )
            expenses = self._ei_sum(
                MoveLine,
                period_domain + [("account_id.account_type", "in", expense_types)],
                "balance",
            )
            receivable = self._ei_sum(
                MoveLine,
                [
                    ("company_id", "=", company.id),
                    ("move_id.state", "=", "posted"),
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("reconciled", "=", False),
                ],
                "amount_residual",
            )
            payable = -self._ei_sum(
                MoveLine,
                [
                    ("company_id", "=", company.id),
                    ("move_id.state", "=", "posted"),
                    ("account_id.account_type", "=", "liability_payable"),
                    ("reconciled", "=", False),
                ],
                "amount_residual",
            )
            result = revenue - expenses
            currency = company.currency_id.name
            company_values = (
                ("revenue", _("Accounting revenue"), revenue),
                ("expenses", _("Accounting expenses"), expenses),
                ("period_result", _("Accounting period result"), result),
                ("receivable", _("Open receivables"), receivable),
                ("payable", _("Open payables"), payable),
            )
            for key, label, value in company_values:
                cards.append(
                    {
                        "key": f"{key}_{company.id}",
                        "label": f"{label} — {company.name}",
                        "value": value,
                        "display_value": f"{value:,.2f} {currency}",
                        "note": _("Posted journal items in company currency"),
                    }
                )
            rows.append(
                {
                    "key": company.id,
                    "company": company.name,
                    "currency": currency,
                    "revenue": f"{revenue:,.2f}",
                    "expenses": f"{expenses:,.2f}",
                    "result": f"{result:,.2f}",
                    "receivable": f"{receivable:,.2f}",
                    "payable": f"{payable:,.2f}",
                }
            )
            if revenue > 0:
                margin = (result / revenue) * 100
                expense_ratio = (expenses / revenue) * 100
                margin_items.append(
                    {
                        "key": company.id,
                        "label": company.name,
                        "value": margin,
                        "display_value": f"{margin:,.1f}%",
                    }
                )
                expense_ratio_items.append(
                    {
                        "key": company.id,
                        "label": company.name,
                        "value": expenses,
                        "target": revenue,
                        "percent": expense_ratio,
                        "display_value": f"{expense_ratio:,.1f}%",
                        "color": "#e84450" if expense_ratio > 100 else "#1b8a7a",
                    }
                )
        return {
            "cards": cards,
            "charts": [
                {
                    "key": "period_result_margin",
                    "type": "bar",
                    "title": _("Period result margin by company"),
                    "subtitle": _("Period result divided by accounting revenue"),
                    "items": margin_items,
                },
                {
                    "key": "expense_revenue_ratio",
                    "type": "gauge",
                    "title": _("Expenses as a share of revenue"),
                    "subtitle": _("Posted expense balances divided by posted revenue"),
                    "items": expense_ratio_items,
                },
            ],
            "tables": [
                {
                    "key": "finance_by_company",
                    "title": _("Verified financial summary by company"),
                    "columns": [
                        {"key": "company", "label": _("Company")},
                        {"key": "currency", "label": _("Currency")},
                        {"key": "revenue", "label": _("Revenue")},
                        {"key": "expenses", "label": _("Expenses")},
                        {"key": "result", "label": _("Period Result")},
                        {"key": "receivable", "label": _("Receivables")},
                        {"key": "payable", "label": _("Payables")},
                    ],
                    "rows": rows,
                }
            ],
            "definitions": {
                "period_result": _(
                    "Posted income account balances minus posted expense account balances."
                ),
                "open_balances": _(
                    "Unreconciled posted receivable and payable journal items."
                ),
            },
        }

    def _ei_sales_dashboard(self, filters):
        SaleOrder = self.env["sale.order"]
        SaleOrder.check_access_rights("read")
        start_dt, end_dt = self._ei_period_datetimes(filters)
        domain = [
            ("company_id", "in", filters["company_ids"]),
            ("state", "in", ("sale", "done")),
            ("date_order", ">=", fields.Datetime.to_string(start_dt)),
            ("date_order", "<", fields.Datetime.to_string(end_dt)),
        ]
        order_count = SaleOrder.search_count(domain)
        period_length = end_dt - start_dt
        previous_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("state", "in", ("sale", "done")),
            (
                "date_order",
                ">=",
                fields.Datetime.to_string(start_dt - period_length),
            ),
            ("date_order", "<", fields.Datetime.to_string(start_dt)),
        ]
        previous_order_count = SaleOrder.search_count(previous_domain)
        cards = [
            {
                "key": "confirmed_sales_orders",
                "label": _("Confirmed sales orders"),
                "value": order_count,
                "display_value": f"{order_count:,}",
                "note": _("Orders confirmed in the selected period"),
                "comparison": self._ei_period_comparison(
                    order_count, previous_order_count
                ),
            }
        ]
        orders = SaleOrder.search(
            domain, order="date_order, id", limit=self._LIVE_ROW_LIMIT + 1
        )
        if len(orders) > self._LIVE_ROW_LIMIT:
            return {
                "status": "requires_precalculation",
                "message": _(
                    "The selected period contains too many sales orders for safe live value analysis. The order count remains exact."
                ),
                "cards": cards,
                "charts": [],
                "tables": [],
                "quality": {"live_row_limit": self._LIVE_ROW_LIMIT},
            }

        company_totals = defaultdict(float)
        customer_totals = defaultdict(float)
        customer_order_counts = defaultdict(int)
        monthly_order_counts = defaultdict(int)
        geo_customer_counts = defaultdict(int)
        partner_has_coordinates = {
            "partner_latitude",
            "partner_longitude",
        } <= set(self.env["res.partner"]._fields)
        for order in orders:
            company_currency = order.company_id.currency_id
            amount = order.currency_id._convert(
                order.amount_untaxed,
                company_currency,
                order.company_id,
                fields.Date.to_date(order.date_order),
            )
            company_totals[order.company_id.id] += amount
            partner = order.partner_id.commercial_partner_id
            customer_totals[(order.company_id.id, partner.id, partner.display_name)] += amount
            customer_order_counts[(partner.id, partner.display_name)] += 1
            month_key = fields.Date.to_string(fields.Date.to_date(order.date_order))[:7]
            monthly_order_counts[month_key] += 1
            if partner_has_coordinates:
                latitude = partner.partner_latitude
                longitude = partner.partner_longitude
                if latitude is not False and longitude is not False and (latitude or longitude):
                    geo_customer_counts[
                        (partner.id, partner.display_name, float(latitude), float(longitude))
                    ] += 1

        companies = self._ei_company_currency_rows(company_totals)
        company_rows = []
        for company_id, amount in sorted(company_totals.items()):
            company = companies[company_id]
            cards.append(
                {
                    "key": f"confirmed_sales_value_{company_id}",
                    "label": _("Confirmed untaxed sales") + f" — {company.name}",
                    "value": amount,
                    "display_value": f"{amount:,.2f} {company.currency_id.name}",
                    "note": _("Converted to company currency on each order date"),
                }
            )
            company_rows.append(
                {
                    "key": company_id,
                    "company": company.name,
                    "value": f"{amount:,.2f}",
                    "currency": company.currency_id.name,
                }
            )

        customer_rows = []
        for (company_id, partner_id, partner_name), amount in sorted(
            customer_totals.items(), key=lambda item: item[1], reverse=True
        )[: self._DETAIL_LIMIT]:
            company = companies[company_id]
            customer_rows.append(
                {
                    "key": f"{company_id}-{partner_id}",
                    "customer": partner_name,
                    "company": company.name,
                    "value": f"{amount:,.2f} {company.currency_id.name}",
                }
            )
        sales_charts = [
            {
                "key": "monthly_sales_order_trend",
                "type": "area",
                "title": _("Monthly confirmed sales order trend"),
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
                "key": "top_customer_order_volume",
                "type": "bar",
                "title": _("Top customers by confirmed order count"),
                "items": [
                    {
                        "key": partner_id,
                        "label": partner_name,
                        "value": count,
                        "display_value": f"{count:,}",
                    }
                    for (partner_id, partner_name), count in sorted(
                        customer_order_counts.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:10]
                ],
            },
        ]
        if geo_customer_counts:
            sales_charts.append(
                {
                    "key": "customer_geographic_distribution",
                    "type": "geo",
                    "title": _("Geographic distribution of confirmed customer orders"),
                    "subtitle": _("Shown only for customers with verified coordinates"),
                    "items": [
                        {
                            "key": partner_id,
                            "label": partner_name,
                            "latitude": latitude,
                            "longitude": longitude,
                            "value": count,
                            "display_value": f"{count:,}",
                        }
                        for (
                            partner_id,
                            partner_name,
                            latitude,
                            longitude,
                        ), count in sorted(
                            geo_customer_counts.items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )[:40]
                    ],
                    "note": _(
                        "Coordinates come from the commercial customer record; customers without coordinates are omitted."
                    ),
                }
            )
        return {
            "cards": cards,
            "charts": sales_charts,
            "tables": [
                {
                    "key": "sales_by_company",
                    "title": _("Confirmed sales by company"),
                    "columns": [
                        {"key": "company", "label": _("Company")},
                        {"key": "value", "label": _("Untaxed Value")},
                        {"key": "currency", "label": _("Currency")},
                    ],
                    "rows": company_rows,
                },
                {
                    "key": "top_customers",
                    "title": _("Top customers by confirmed untaxed sales"),
                    "columns": [
                        {"key": "customer", "label": _("Customer")},
                        {"key": "company", "label": _("Company")},
                        {"key": "value", "label": _("Value")},
                    ],
                    "rows": customer_rows,
                },
            ],
        }

    def _ei_stock_scope(self, filters):
        warehouse_ids = filters.get("warehouse_ids", [])
        if not warehouse_ids:
            return self.env["stock.warehouse"].browse([]), []
        warehouses = self.env["stock.warehouse"].sudo().browse(
            warehouse_ids
        ).exists()
        return warehouses, self._ei_internal_location_ids(warehouses)

    def _ei_product_dashboard(self, filters):
        MoveLine = self.env["stock.move.line"]
        Quant = self.env["stock.quant"]
        MoveLine.check_access_rights("read")
        Quant.check_access_rights("read")
        _warehouses, location_ids = self._ei_stock_scope(filters)
        start_dt, end_dt = self._ei_period_datetimes(filters)
        base_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("move_id.state", "=", "done"),
            ("date", ">=", fields.Datetime.to_string(start_dt)),
            ("date", "<", fields.Datetime.to_string(end_dt)),
        ]
        delivered = self._ei_quantity_by_product(
            base_domain
            + [
                ("location_id", "in", location_ids),
                ("location_dest_id.usage", "=", "customer"),
            ]
        )
        returned = self._ei_quantity_by_product(
            base_domain
            + [
                ("location_id.usage", "=", "customer"),
                ("location_dest_id", "in", location_ids),
            ]
        )
        quant_groups = Quant.read_group(
            [
                ("company_id", "in", filters["company_ids"]),
                ("location_id", "in", location_ids),
            ],
            ["quantity:sum", "reserved_quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        stock = {
            group["product_id"][0]: (
                group.get("quantity", 0.0),
                group.get("reserved_quantity", 0.0),
            )
            for group in quant_groups
            if group.get("product_id")
        }
        product_ids = set(delivered) | set(returned) | set(stock)
        products = {
            product.id: product
            for product in self.env["product.product"].browse(product_ids).exists()
        }
        rows = []
        for product_id in product_ids:
            product = products.get(product_id)
            if not product:
                continue
            on_hand, reserved = stock.get(product_id, (0.0, 0.0))
            delivered_qty = delivered.get(product_id, 0.0)
            returned_qty = returned.get(product_id, 0.0)
            rows.append(
                {
                    "key": product_id,
                    "product": product.display_name,
                    "category": product.categ_id.display_name,
                    "sold": delivered_qty,
                    "returned": returned_qty,
                    "net": delivered_qty - returned_qty,
                    "on_hand": on_hand,
                    "available": on_hand - reserved,
                    "uom": product.uom_id.name,
                }
            )
        rows.sort(key=lambda row: (row["net"], row["on_hand"]), reverse=True)
        rows = rows[: self._DETAIL_LIMIT]
        product_chart_items = [
            {
                "key": row["key"],
                "label": row["product"],
                "value": row["net"],
                "display_value": f"{row['net']:,.2f} {row['uom']}",
            }
            for row in rows[:12]
        ]
        category_counts = defaultdict(int)
        for row in rows:
            category_counts[row["category"]] += 1
        for row in rows:
            for key in ("sold", "returned", "net", "on_hand", "available"):
                row[key] = f"{row[key]:,.2f}"
        return {
            "cards": [
                {
                    "key": "products_with_stock_or_sales",
                    "label": _("Products with stock or customer movement"),
                    "value": len(product_ids),
                    "display_value": f"{len(product_ids):,}",
                    "note": _("Distinct products in the selected warehouse scope"),
                },
                {
                    "key": "products_sold",
                    "label": _("Products delivered to customers"),
                    "value": len([value for value in delivered.values() if value]),
                    "display_value": f"{len([value for value in delivered.values() if value]):,}",
                    "note": _("Completed customer deliveries in the selected period"),
                },
            ],
            "charts": [
                {
                    "key": "top_product_net_movement",
                    "type": "column",
                    "title": _("Top products by net customer movement"),
                    "subtitle": _("Quantities remain in each product unit of measure"),
                    "items": product_chart_items,
                },
                {
                    "key": "product_category_heatmap",
                    "type": "heatmap",
                    "title": _("Product activity heatmap by category"),
                    "items": [
                        {
                            "key": category,
                            "label": category,
                            "value": count,
                            "display_value": f"{count:,}",
                        }
                        for category, count in sorted(
                            category_counts.items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )[:20]
                    ],
                },
            ],
            "tables": [
                {
                    "key": "product_performance",
                    "title": _("Product movement and current availability"),
                    "columns": [
                        {"key": "product", "label": _("Product")},
                        {"key": "category", "label": _("Category")},
                        {"key": "sold", "label": _("Delivered")},
                        {"key": "returned", "label": _("Returned")},
                        {"key": "net", "label": _("Net Sales Quantity")},
                        {"key": "on_hand", "label": _("On Hand")},
                        {"key": "available", "label": _("Available")},
                        {"key": "uom", "label": _("Unit")},
                    ],
                    "rows": rows,
                }
            ],
            "quality": {"detail_limit": self._DETAIL_LIMIT},
        }

    def _ei_quantity_by_product(self, domain):
        groups = self.env["stock.move.line"].read_group(
            domain,
            ["quantity_product_uom:sum"],
            ["product_id"],
            lazy=False,
        )
        return {
            group["product_id"][0]: group.get("quantity_product_uom", 0.0)
            for group in groups
            if group.get("product_id")
        }

    def _ei_hr_dashboard(self, filters):
        Employee = self.env["hr.employee"]
        Attendance = self.env["hr.attendance"]
        Leave = self.env["hr.leave"]
        Employee.check_access_rights("read")
        start_dt, end_dt = self._ei_period_datetimes(filters)
        employee_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("active", "=", True),
        ]
        headcount = Employee.search_count(employee_domain)
        department_groups = Employee.read_group(
            employee_domain,
            ["id:count"],
            ["department_id"],
            lazy=False,
        )
        department_rows = [
            {
                "key": group["department_id"][0] if group.get("department_id") else "none",
                "department": group["department_id"][1]
                if group.get("department_id")
                else _("Without Department"),
                "employees": group.get("department_id_count", group.get("__count", 0)),
            }
            for group in department_groups
        ]
        attendance_hours = None
        if Attendance.check_access_rights("read", raise_exception=False):
            attendance_hours = self._ei_sum(
                Attendance,
                [
                    ("employee_id.company_id", "in", filters["company_ids"]),
                    ("check_in", ">=", fields.Datetime.to_string(start_dt)),
                    ("check_in", "<", fields.Datetime.to_string(end_dt)),
                ],
                "worked_hours",
            )
        leave_count = None
        if Leave.check_access_rights("read", raise_exception=False):
            leave_count = Leave.search_count(
                [
                    ("employee_id.company_id", "in", filters["company_ids"]),
                    ("state", "=", "validate"),
                    ("date_from", "<", fields.Datetime.to_string(end_dt)),
                    ("date_to", ">=", fields.Datetime.to_string(start_dt)),
                ]
            )
        cards = [
                {
                    "key": "active_employees",
                    "label": _("Active employees"),
                    "value": headcount,
                    "display_value": f"{headcount:,}",
                    "note": _("Employees active in the permitted companies"),
                },
                {
                    "key": "departments",
                    "label": _("Departments with active employees"),
                    "value": len(department_rows),
                    "display_value": f"{len(department_rows):,}",
                    "note": _("Current organizational distribution"),
                },
            ]
        if attendance_hours is not None:
            cards.append(
                {
                    "key": "attendance_hours",
                    "label": _("Recorded attendance hours"),
                    "value": attendance_hours,
                    "display_value": f"{attendance_hours:,.2f}",
                    "note": _("Attendance records beginning in the selected period"),
                }
            )
        if leave_count is not None:
            cards.append(
                {
                    "key": "approved_leave_requests",
                    "label": _("Approved leave requests"),
                    "value": leave_count,
                    "display_value": f"{leave_count:,}",
                    "note": _("Approved leave requests overlapping the selected period"),
                }
            )
        return {
            "cards": cards,
            "charts": [
                {
                    "key": "employees_by_department_chart",
                    "type": "column",
                    "title": _("Active employees by department"),
                    "items": [
                        {
                            "key": row["key"],
                            "label": row["department"],
                            "value": row["employees"],
                            "display_value": f"{row['employees']:,}",
                        }
                        for row in sorted(
                            department_rows,
                            key=lambda item: item["employees"],
                            reverse=True,
                        )[:16]
                    ],
                }
            ],
            "tables": [
                {
                    "key": "employees_by_department",
                    "title": _("Active employees by department"),
                    "columns": [
                        {"key": "department", "label": _("Department")},
                        {"key": "employees", "label": _("Employees")},
                    ],
                    "rows": department_rows,
                }
            ],
        }

    def _ei_operations_dashboard(self, filters):
        Production = self.env["mrp.production"]
        Production.check_access_rights("read")
        start_dt, end_dt = self._ei_period_datetimes(filters)
        company_domain = [("company_id", "in", filters["company_ids"])]
        open_domain = company_domain + [("state", "not in", ("done", "cancel"))]
        open_count = Production.search_count(open_domain)
        overdue_count = Production.search_count(
            open_domain
            + [
                ("date_deadline", "!=", False),
                ("date_deadline", "<", fields.Datetime.to_string(fields.Datetime.now())),
            ]
        )
        completed_count = Production.search_count(
            company_domain
            + [
                ("state", "=", "done"),
                ("date_finished", ">=", fields.Datetime.to_string(start_dt)),
                ("date_finished", "<", fields.Datetime.to_string(end_dt)),
            ]
        )
        state_groups = Production.read_group(
            company_domain,
            ["id:count"],
            ["state"],
            lazy=False,
        )
        selection = dict(
            Production._fields["state"]._description_selection(self.env)
        )
        rows = [
            {
                "key": group["state"],
                "state": selection.get(group["state"], group["state"]),
                "orders": group.get("state_count", group.get("__count", 0)),
            }
            for group in state_groups
        ]
        return {
            "cards": [
                {
                    "key": "open_manufacturing_orders",
                    "label": _("Open manufacturing orders"),
                    "value": open_count,
                    "display_value": f"{open_count:,}",
                    "note": _("Manufacturing orders not done or cancelled"),
                },
                {
                    "key": "overdue_manufacturing_orders",
                    "label": _("Overdue manufacturing orders"),
                    "value": overdue_count,
                    "display_value": f"{overdue_count:,}",
                    "note": _("Open orders past their deadline"),
                },
                {
                    "key": "completed_manufacturing_orders",
                    "label": _("Completed manufacturing orders"),
                    "value": completed_count,
                    "display_value": f"{completed_count:,}",
                    "note": _("Orders completed in the selected period"),
                },
            ],
            "charts": [
                {
                    "key": "manufacturing_states_chart",
                    "type": "bar",
                    "title": _("Manufacturing orders by status"),
                    "items": [
                        {
                            "key": row["key"],
                            "label": row["state"],
                            "value": row["orders"],
                            "display_value": f"{row['orders']:,}",
                        }
                        for row in rows
                    ],
                },
                {
                    "key": "overdue_manufacturing_share",
                    "type": "gauge",
                    "title": _("Overdue share of open manufacturing orders"),
                    "items": [
                        {
                            "key": "overdue_share",
                            "label": _("Overdue open orders"),
                            "value": overdue_count,
                            "target": open_count,
                            "percent": (overdue_count / open_count * 100)
                            if open_count
                            else 0.0,
                            "display_value": f"{overdue_count:,} / {open_count:,}",
                            "color": "#e84450",
                        }
                    ],
                },
            ],
            "tables": [
                {
                    "key": "manufacturing_states",
                    "title": _("Manufacturing orders by status"),
                    "columns": [
                        {"key": "state", "label": _("Status")},
                        {"key": "orders", "label": _("Orders")},
                    ],
                    "rows": rows,
                }
            ],
        }

    def _ei_forecast_dashboard(self, filters):
        MoveLine = self.env["stock.move.line"]
        Quant = self.env["stock.quant"]
        MoveLine.check_access_rights("read")
        Quant.check_access_rights("read")
        _warehouses, location_ids = self._ei_stock_scope(filters)
        start_dt, end_dt = self._ei_period_datetimes(filters)
        history_days = max((filters["date_to"] - filters["date_from"]).days + 1, 1)
        move_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("move_id.state", "=", "done"),
            ("date", ">=", fields.Datetime.to_string(start_dt)),
            ("date", "<", fields.Datetime.to_string(end_dt)),
            ("location_id", "in", location_ids),
            ("location_dest_id.usage", "=", "customer"),
        ]
        movement_groups = MoveLine.read_group(
            move_domain,
            ["quantity_product_uom:sum"],
            ["product_id"],
            lazy=False,
        )
        demand = {
            group["product_id"][0]: (
                group.get("quantity_product_uom", 0.0),
                group.get("product_id_count", group.get("__count", 0)),
            )
            for group in movement_groups
            if group.get("product_id")
        }
        quant_groups = Quant.read_group(
            [
                ("company_id", "in", filters["company_ids"]),
                ("location_id", "in", location_ids),
            ],
            ["quantity:sum", "reserved_quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        available = {
            group["product_id"][0]: group.get("quantity", 0.0)
            - group.get("reserved_quantity", 0.0)
            for group in quant_groups
            if group.get("product_id")
        }
        products = {
            product.id: product
            for product in self.env["product.product"].browse(demand).exists()
        }
        rows = []
        for product_id, (historical_qty, movement_count) in demand.items():
            product = products.get(product_id)
            if not product or historical_qty <= 0:
                continue
            daily_rate = historical_qty / history_days
            available_qty = max(available.get(product_id, 0.0), 0.0)
            demand_30 = daily_rate * 30
            shortage_30 = max(demand_30 - available_qty, 0.0)
            days_cover = available_qty / daily_rate if daily_rate else 0.0
            confidence = (
                _("High")
                if history_days >= 180 and movement_count >= 12
                else (_("Medium") if history_days >= 90 and movement_count >= 6 else _("Low"))
            )
            rows.append(
                {
                    "key": product_id,
                    "product": product.display_name,
                    "available": available_qty,
                    "daily_rate": daily_rate,
                    "demand_30": demand_30,
                    "shortage_30": shortage_30,
                    "days_cover": days_cover,
                    "confidence": confidence,
                    "uom": product.uom_id.name,
                }
            )
        analyzed_count = len(rows)
        at_risk = len([row for row in rows if row["shortage_30"] > 0])
        low_confidence = len([row for row in rows if row["confidence"] == _("Low")])
        rows.sort(key=lambda row: (row["shortage_30"], -row["days_cover"]), reverse=True)
        rows = rows[: self._DETAIL_LIMIT]
        coverage_items = [
            {
                "key": row["key"],
                "label": row["product"],
                "value": row["available"],
                "target": row["demand_30"],
                "percent": min(
                    (row["available"] / row["demand_30"] * 100)
                    if row["demand_30"]
                    else 0.0,
                    100.0,
                ),
                "display_value": f"{row['available']:,.2f} / {row['demand_30']:,.2f} {row['uom']}",
                "target_label": _("Available quantity versus 30-day baseline demand"),
            }
            for row in rows[:12]
        ]
        shortage_heat_items = [
            {
                "key": row["key"],
                "label": row["product"],
                "value": (row["shortage_30"] / row["demand_30"] * 100)
                if row["demand_30"]
                else 0.0,
                "display_value": f"{row['shortage_30']:,.2f} {row['uom']}",
                "color": "232, 68, 80",
            }
            for row in rows[:20]
        ]
        for row in rows:
            for key in ("available", "daily_rate", "demand_30", "shortage_30", "days_cover"):
                row[key] = f"{row[key]:,.2f}"
        return {
            "status": "baseline_forecast",
            "message": _(
                "This is a transparent operational baseline based on completed customer deliveries. Low-confidence products require more history before advanced forecasting."
            ),
            "cards": [
                {
                    "key": "forecast_products",
                    "label": _("Products analyzed"),
                    "value": analyzed_count,
                    "display_value": f"{analyzed_count:,}",
                    "note": _("Products with completed customer demand in the selected history"),
                },
                {
                    "key": "shortage_risk_30",
                    "label": _("Potential shortages within 30 days"),
                    "value": at_risk,
                    "display_value": f"{at_risk:,}",
                    "note": _("Baseline demand exceeds currently available quantity"),
                },
                {
                    "key": "low_confidence_products",
                    "label": _("Low-confidence baselines"),
                    "value": low_confidence,
                    "display_value": f"{low_confidence:,}",
                    "note": _("Insufficient history or completed movement count"),
                },
            ],
            "charts": [
                {
                    "key": "forecast_coverage_progress",
                    "type": "progress",
                    "title": _("Available quantity versus 30-day demand"),
                    "items": coverage_items,
                },
                {
                    "key": "forecast_shortage_heatmap",
                    "type": "heatmap",
                    "title": _("Expected shortage heatmap"),
                    "subtitle": _("Higher intensity means a larger share of baseline demand is uncovered"),
                    "items": shortage_heat_items,
                },
            ],
            "tables": [
                {
                    "key": "demand_baseline",
                    "title": _("Thirty-day demand and availability baseline"),
                    "columns": [
                        {"key": "product", "label": _("Product")},
                        {"key": "available", "label": _("Available")},
                        {"key": "daily_rate", "label": _("Daily Demand")},
                        {"key": "demand_30", "label": _("30-Day Demand")},
                        {"key": "shortage_30", "label": _("Expected Shortage")},
                        {"key": "days_cover", "label": _("Days of Cover")},
                        {"key": "confidence", "label": _("Confidence")},
                        {"key": "uom", "label": _("Unit")},
                    ],
                    "rows": rows,
                }
            ],
            "quality": {
                "method": "completed_customer_delivery_daily_baseline",
                "history_days": history_days,
                "detail_limit": self._DETAIL_LIMIT,
            },
        }

    def _ei_risk_dashboard(self, filters):
        rows = []

        def add_risk(key, severity, risk, metric, recommendation):
            rows.append(
                {
                    "key": key,
                    "severity": severity,
                    "risk": risk,
                    "metric": metric,
                    "recommendation": recommendation,
                }
            )

        if self._ei_can_read("stock.quant") and filters.get("warehouse_ids"):
            warehouses, location_ids = self._ei_stock_scope(filters)
            negative_count = self.env["stock.quant"].search_count(
                [
                    ("company_id", "in", filters["company_ids"]),
                    ("location_id", "in", location_ids),
                    ("quantity", "<", 0),
                ]
            )
            if negative_count:
                add_risk(
                    "negative_stock",
                    _("High") if negative_count > 10 else _("Medium"),
                    _("Negative stock positions"),
                    f"{negative_count:,}",
                    _("Review the related stock moves and inventory controls."),
                )

        if self._ei_can_read("account.move"):
            overdue_invoices = self.env["account.move"].search_count(
                [
                    ("company_id", "in", filters["company_ids"]),
                    ("state", "=", "posted"),
                    ("move_type", "=", "out_invoice"),
                    ("payment_state", "not in", ("paid", "reversed")),
                    ("invoice_date_due", "<", fields.Date.context_today(self)),
                    ("amount_residual", ">", 0),
                ]
            )
            if overdue_invoices:
                add_risk(
                    "overdue_receivables",
                    _("High") if overdue_invoices > 20 else _("Medium"),
                    _("Overdue customer invoices"),
                    f"{overdue_invoices:,}",
                    _("Prioritize collection and validate disputed balances."),
                )

        if self._ei_can_read("stock.picking"):
            overdue_receipts = self.env["stock.picking"].search_count(
                [
                    ("company_id", "in", filters["company_ids"]),
                    ("picking_type_id.code", "=", "incoming"),
                    ("purchase_id", "!=", False),
                    ("state", "not in", ("done", "cancel")),
                    ("scheduled_date", "<", fields.Datetime.now()),
                ]
            )
            if overdue_receipts:
                add_risk(
                    "overdue_receipts",
                    _("High") if overdue_receipts > 20 else _("Medium"),
                    _("Overdue purchase receipts"),
                    f"{overdue_receipts:,}",
                    _("Escalate overdue receipts with the responsible suppliers."),
                )

        if self._ei_can_read("mrp.production"):
            overdue_mos = self.env["mrp.production"].search_count(
                [
                    ("company_id", "in", filters["company_ids"]),
                    ("state", "not in", ("done", "cancel")),
                    ("date_deadline", "!=", False),
                    ("date_deadline", "<", fields.Datetime.now()),
                ]
            )
            if overdue_mos:
                add_risk(
                    "overdue_manufacturing",
                    _("High") if overdue_mos > 10 else _("Medium"),
                    _("Overdue manufacturing orders"),
                    f"{overdue_mos:,}",
                    _("Review material availability and production bottlenecks."),
                )

        severity_order = {_("Critical"): 4, _("High"): 3, _("Medium"): 2, _("Low"): 1}
        rows.sort(key=lambda row: severity_order.get(row["severity"], 0), reverse=True)
        high_count = len([row for row in rows if row["severity"] in (_("Critical"), _("High"))])
        risk_level = {_("Critical"): 4, _("High"): 3, _("Medium"): 2, _("Low"): 1}
        risk_heat_items = [
            {
                "key": row["key"],
                "label": row["risk"],
                "value": risk_level.get(row["severity"], 0),
                "percent": risk_level.get(row["severity"], 0) * 25,
                "display_value": row["severity"],
                "color": "232, 68, 80",
            }
            for row in rows
        ]
        return {
            "cards": [
                {
                    "key": "verified_risks",
                    "label": _("Verified active risks"),
                    "value": len(rows),
                    "display_value": f"{len(rows):,}",
                    "note": _("Rule-based exceptions supported by current Odoo records"),
                },
                {
                    "key": "high_risks",
                    "label": _("Critical and high risks"),
                    "value": high_count,
                    "display_value": f"{high_count:,}",
                    "note": _("Risks requiring priority review"),
                },
            ],
            "charts": [
                {
                    "key": "risk_severity_heatmap",
                    "type": "heatmap",
                    "title": _("Verified risk severity heatmap"),
                    "items": risk_heat_items,
                },
                {
                    "key": "high_risk_share",
                    "type": "gauge",
                    "title": _("Critical and high risk share"),
                    "items": [
                        {
                            "key": "high_risk_share",
                            "label": _("Critical and high risks"),
                            "value": high_count,
                            "target": len(rows),
                            "percent": (high_count / len(rows) * 100)
                            if rows
                            else 0.0,
                            "display_value": f"{high_count:,} / {len(rows):,}",
                            "color": "#e84450",
                        }
                    ],
                },
            ],
            "tables": [
                {
                    "key": "risk_register",
                    "title": _("Executive risk register"),
                    "columns": [
                        {"key": "severity", "label": _("Severity")},
                        {"key": "risk", "label": _("Risk")},
                        {"key": "metric", "label": _("Affected Records")},
                        {"key": "recommendation", "label": _("Recommended Action")},
                    ],
                    "rows": rows,
                }
            ],
        }

    def _ei_executive_dashboard(self, filters):
        finance = self._ei_finance_dashboard(filters)
        risk = self._ei_risk_dashboard(filters)
        cards = list(finance["cards"])
        cards.extend(risk["cards"])

        if self._ei_can_read("sale.order"):
            start_dt, end_dt = self._ei_period_datetimes(filters)
            sales_count = self.env["sale.order"].search_count(
                [
                    ("company_id", "in", filters["company_ids"]),
                    ("state", "in", ("sale", "done")),
                    ("date_order", ">=", fields.Datetime.to_string(start_dt)),
                    ("date_order", "<", fields.Datetime.to_string(end_dt)),
                ]
            )
            cards.append(
                {
                    "key": "executive_sales_orders",
                    "label": _("Confirmed sales orders"),
                    "value": sales_count,
                    "display_value": f"{sales_count:,}",
                    "note": _("Orders confirmed in the selected period"),
                }
            )
        access = self.env.user._ei_effective_access()
        if access["hr_access"] != "none" and self._ei_can_read("hr.employee"):
            employee_count = self.env["hr.employee"].search_count(
                [
                    ("company_id", "in", filters["company_ids"]),
                    ("active", "=", True),
                ]
            )
            cards.append(
                {
                    "key": "executive_headcount",
                    "label": _("Active employees"),
                    "value": employee_count,
                    "display_value": f"{employee_count:,}",
                    "note": _("Employees active in the permitted companies"),
                }
            )
        return {
            "cards": cards,
            "charts": finance.get("charts", []) + risk.get("charts", []),
            "tables": [
                finance["tables"][0],
                {
                    **risk["tables"][0],
                    "rows": risk["tables"][0]["rows"][:5],
                    "title": _("Top five verified risks"),
                },
            ],
            "definitions": finance.get("definitions", {}),
        }

