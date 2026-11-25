from collections import defaultdict
from datetime import timedelta

import pytz

from odoo import api, fields, models
from odoo.osv.expression import AND


class ReportSaleDetails(models.AbstractModel):
    _inherit = "report.point_of_sale.report_saledetails"

    @api.model
    def _get_sale_details_order_domain(
        self, date_start=False, date_stop=False, config_ids=False, session_ids=False
    ):
        domain = [("state", "in", ["paid", "invoiced", "done"])]
        if session_ids:
            return AND([domain, [("session_id", "in", session_ids)]])

        if date_start:
            date_start = fields.Datetime.to_datetime(date_start)
        else:
            user_tz = pytz.timezone(
                self.env.context.get("tz") or self.env.user.tz or "UTC"
            )
            today = user_tz.localize(
                fields.Datetime.to_datetime(fields.Date.context_today(self))
            )
            date_start = today.astimezone(pytz.UTC).replace(tzinfo=None)

        if date_stop:
            date_stop = fields.Datetime.to_datetime(date_stop)
            if date_stop < date_start:
                date_stop = date_start + timedelta(days=1, seconds=-1)
        else:
            date_stop = date_start + timedelta(days=1, seconds=-1)

        period_domain = [
            ("date_order", ">=", fields.Datetime.to_string(date_start)),
            ("date_order", "<=", fields.Datetime.to_string(date_stop)),
        ]
        if config_ids:
            period_domain.append(("config_id", "in", config_ids))
        return AND([domain, period_domain])

    @api.model
    def _get_sale_details_currency(self, config_ids=False, session_ids=False):
        if config_ids:
            currencies = self.env["pos.config"].browse(config_ids).mapped(
                "currency_id"
            )
        else:
            currencies = self.env["pos.session"].browse(session_ids).mapped(
                "config_id.currency_id"
            )
        if currencies and all(
            currency == currencies[0] for currency in currencies
        ):
            return currencies[0]
        return self.env.company.currency_id

    @api.model
    def _convert_order_amount(self, order, amount, report_currency):
        order_currency = order.pricelist_id.currency_id
        if order_currency == report_currency:
            return amount
        return order_currency._convert(
            amount,
            report_currency,
            order.company_id,
            order.date_order or fields.Date.context_today(self),
        )

    @api.model
    def _format_local_datetime(self, value):
        if not value:
            return ""
        return fields.Datetime.context_timestamp(self, value).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    @api.model
    def _aggregate_product_ranking(self, lines):
        """Rank products by net units, then net sales, with refunds separate."""
        totals = defaultdict(
            lambda: {
                "product_id": False,
                "product_name": "",
                "code": "",
                "uom": "",
                "sold_quantity": 0.0,
                "refund_quantity": 0.0,
                "net_quantity": 0.0,
                "net_amount": 0.0,
            }
        )
        for line in lines:
            key = line["product_id"]
            total = totals[key]
            for field in ("product_id", "product_name", "code", "uom"):
                total[field] = line.get(field) or ""
            quantity = line["quantity"]
            total["sold_quantity"] += max(quantity, 0.0)
            total["refund_quantity"] += max(-quantity, 0.0)
            total["net_quantity"] += quantity
            total["net_amount"] += line["amount"]
        ranked = sorted(
            totals.values(),
            key=lambda line: (
                -round(line["net_quantity"], 6),
                -line["net_amount"],
                line["product_name"].casefold(),
                line["product_id"],
            ),
        )
        return [dict(line, rank=index) for index, line in enumerate(ranked, 1)]

    @api.model
    def _prepare_product_ranking(self, orders, report_currency, convert_amount=None):
        convert_amount = convert_amount or (
            lambda order, amount: self._convert_order_amount(
                order, amount, report_currency
            )
        )
        return self._aggregate_product_ranking(
            {
                "product_id": line.product_id.id,
                "product_name": line.product_id.display_name,
                "code": line.product_id.default_code,
                "uom": line.product_uom_id.display_name,
                "quantity": line.qty,
                "amount": convert_amount(line.order_id, line.price_subtotal_incl),
            }
            for line in orders.lines
            if line.product_id and line.qty
        )

    @api.model
    def _prepare_refund_order_details(self, orders, report_currency):
        result = []
        refund_orders = orders.filtered(
            lambda order: any(line.qty < 0 for line in order.lines)
        ).sorted(key=lambda order: (order.date_order, order.id))
        for order in refund_orders:
            refund_lines = order.lines.filtered(lambda line: line.qty < 0)
            original_orders = refund_lines.mapped(
                "refunded_orderline_id.order_id"
            )
            payment_parts = []
            for payment in order.payment_ids:
                amount = self._convert_order_amount(
                    order, payment.amount, report_currency
                )
                payment_parts.append(
                    "%s: %s"
                    % (payment.payment_method_id.display_name, report_currency.format(amount))
                )

            lines = []
            for line in refund_lines:
                original_order = line.refunded_orderline_id.order_id
                lines.append(
                    {
                        "product_name": line.full_product_name
                        or line.product_id.display_name,
                        "code": line.product_id.default_code or "",
                        "quantity": line.qty,
                        "uom": line.product_uom_id.display_name,
                        "price_unit": (
                            self._convert_order_amount(
                                order, line.price_unit, report_currency
                            )
                        ),
                        "discount": line.discount,
                        "subtotal": self._convert_order_amount(
                            order, line.price_subtotal, report_currency
                        ),
                        "total": (
                            self._convert_order_amount(
                                order, line.price_subtotal_incl, report_currency
                            )
                        ),
                        "tax": (
                            self._convert_order_amount(
                                order,
                                line.price_subtotal_incl - line.price_subtotal,
                                report_currency,
                            )
                        ),
                        "original_receipt": original_order.pos_reference or "",
                        "original_order": original_order.name or "",
                        "original_invoice": original_order.account_move.name
                        if original_order.account_move
                        else "",
                        "customer_note": line.customer_note or "",
                    }
                )

            result.append(
                {
                    "order_reference": order.name,
                    "receipt_number": order.pos_reference or order.name,
                    "order_number": order.tracking_number or "",
                    "date": self._format_local_datetime(order.date_order),
                    "cashier": (
                        order.cashier
                        if "cashier" in order._fields
                        else order.user_id.display_name
                    ) or order.user_id.display_name,
                    "customer": order.partner_id.display_name or "عميل نقدي",
                    "pos_name": order.config_id.display_name,
                    "session_name": order.session_id.name,
                    "refund_invoice": order.account_move.name
                    if order.account_move
                    else "",
                    "original_receipts": ", ".join(
                        filter(None, original_orders.mapped("pos_reference"))
                    ),
                    "original_order_numbers": ", ".join(
                        filter(None, original_orders.mapped("tracking_number"))
                    ),
                    "original_invoices": ", ".join(
                        filter(None, original_orders.mapped("account_move.name"))
                    ),
                    "payments": "، ".join(payment_parts),
                    "refund_subtotal": sum(line["subtotal"] for line in lines),
                    "refund_total": sum(line["total"] for line in lines),
                    "refund_tax": sum(line["tax"] for line in lines),
                    "has_sale_lines": any(line.qty > 0 for line in order.lines),
                    "amount_total": (
                        self._convert_order_amount(
                            order, order.amount_total, report_currency
                        )
                    ),
                    "amount_tax": (
                        self._convert_order_amount(
                            order, order.amount_tax, report_currency
                        )
                    ),
                    "note": order.note or "",
                    "lines": lines,
                }
            )
        return result

    @api.model
    def get_sale_details(
        self, date_start=False, date_stop=False, config_ids=False, session_ids=False
    ):
        result = super().get_sale_details(
            date_start=date_start,
            date_stop=date_stop,
            config_ids=config_ids,
            session_ids=session_ids,
        )
        result["products"] = sorted(
            result.get("products", []),
            key=lambda category: (
                -category.get("qty", 0.0),
                str(category.get("name") or "").casefold(),
            ),
        )
        for category in result["products"]:
            category["products"] = sorted(
                category.get("products", []),
                key=lambda line: (
                    -line.get("quantity", 0.0),
                    -line.get("base_amount", 0.0),
                    (line.get("product_name") or "").casefold(),
                ),
            )
        result["refund_products"] = sorted(
            result.get("refund_products", []),
            key=lambda category: (
                -abs(category.get("qty", 0.0)),
                str(category.get("name") or "").casefold(),
            ),
        )
        for category in result["refund_products"]:
            category["products"] = sorted(
                category.get("products", []),
                key=lambda line: (
                    -abs(line.get("quantity", 0.0)),
                    (line.get("product_name") or "").casefold(),
                ),
            )

        domain = self._get_sale_details_order_domain(
            date_start, date_stop, config_ids, session_ids
        )
        orders = self.env["pos.order"].search(domain, order="date_order, id")
        report_currency = self._get_sale_details_currency(
            config_ids, session_ids
        )
        result["ej_report_currency_id"] = report_currency.id
        result["refund_order_details"] = self._prepare_refund_order_details(
            orders, report_currency
        )
        result["top_selling_products"] = self._prepare_product_ranking(
            orders, report_currency
        )
        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        values = super()._get_report_values(docids, data=data)
        values["ej_report_currency"] = self.env["res.currency"].browse(
            values["ej_report_currency_id"]
        )
        return values
