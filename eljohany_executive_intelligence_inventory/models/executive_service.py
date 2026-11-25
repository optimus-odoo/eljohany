from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class ExecutiveIntelligenceService(models.AbstractModel):
    _inherit = "executive.intelligence.service"

    _INVENTORY_DETAIL_LIMIT_PER_WAREHOUSE = 50

    def _ei_supported_dashboard_codes(self):
        return super()._ei_supported_dashboard_codes() | {"inventory"}

    @api.model
    def get_bootstrap(self):
        result = super().get_bootstrap()
        access = self.env.user._ei_effective_access()
        # Warehouse names are access-scope metadata. The ids have already been
        # authorization-filtered by _ei_effective_access, so sudo here avoids
        # requiring a separate stock.warehouse ACL for purchase-only viewers.
        warehouses = self.env["stock.warehouse"].sudo().browse(
            access.get("warehouse_ids", [])
        ).exists()
        result["warehouses"] = [
            {
                "id": warehouse.id,
                "name": warehouse.name,
                "company_id": warehouse.company_id.id,
            }
            for warehouse in warehouses
        ]
        return result

    def _ei_normalize_filters(self, filters, access):
        result = super()._ei_normalize_filters(filters, access)
        filters = dict(filters or {})
        allowed_warehouses = set(access.get("warehouse_ids", []))
        requested = (
            filters["warehouse_ids"]
            if "warehouse_ids" in filters
            else sorted(allowed_warehouses)
        )
        try:
            requested = {int(warehouse_id) for warehouse_id in requested}
        except (TypeError, ValueError) as error:
            raise UserError(_("Invalid warehouse filter.")) from error
        if requested and not requested <= allowed_warehouses:
            raise AccessError(_("The selected warehouse scope is not allowed."))
        result["warehouse_ids"] = sorted(requested)
        return result

    def _ei_get_dashboard_data(self, dashboard_code, filters, access):
        if dashboard_code == "inventory":
            return self._ei_inventory_dashboard(filters)
        return super()._ei_get_dashboard_data(dashboard_code, filters, access)

    def _ei_no_warehouse_payload(self):
        """Return a safe, renderable empty scope instead of an RPC failure."""
        return {
            "status": "warehouse_scope_unavailable",
            "message": _("No analytics warehouse is configured for this user."),
            "cards": [],
            "charts": [],
            "tables": [],
            "quality": {"warehouse_scope": "empty"},
        }

    def _ei_inventory_dashboard(self, filters):
        warehouse_ids = filters.get("warehouse_ids", [])
        if not warehouse_ids:
            return self._ei_no_warehouse_payload()

        Quant = self.env["stock.quant"]
        Orderpoint = self.env["stock.warehouse.orderpoint"]
        Quant.check_access_rights("read")
        Orderpoint.check_access_rights("read")
        # Warehouse records here are already limited to the authorized ids.
        # Read their structural metadata with sudo so a dormant third-party
        # warehouse rule cannot turn a valid analytics scope into an RPC error.
        warehouses = self.env["stock.warehouse"].sudo().browse(
            warehouse_ids
        ).exists()

        all_location_ids = self._ei_internal_location_ids(warehouses)
        base_domain = [
            ("company_id", "in", filters["company_ids"]),
            ("location_id", "in", all_location_ids),
        ]
        stock_position_count = Quant.search_count(base_domain + [("quantity", "!=", 0)])
        negative_position_count = Quant.search_count(base_domain + [("quantity", "<", 0)])
        location_groups = Quant.read_group(
            base_domain + [("quantity", "!=", 0)],
            ["location_id"],
            ["location_id"],
            lazy=False,
        )
        replenishment_count = Orderpoint.search_count(
            [
                ("company_id", "in", filters["company_ids"]),
                ("location_id", "in", all_location_ids),
                ("qty_to_order", ">", 0),
            ]
        )

        cards = [
            {
                "key": "stock_positions",
                "label": _("Stock positions with quantity"),
                "value": stock_position_count,
                "display_value": f"{stock_position_count:,}",
                "note": _("Exact count of non-zero internal stock quants"),
            },
            {
                "key": "stocked_locations",
                "label": _("Internal locations with stock"),
                "value": len(location_groups),
                "display_value": f"{len(location_groups):,}",
                "note": _("Locations in the permitted warehouses"),
            },
            {
                "key": "negative_positions",
                "label": _("Negative stock positions"),
                "value": negative_position_count,
                "display_value": f"{negative_position_count:,}",
                "note": _("Quant records whose on-hand quantity is below zero"),
            },
            {
                "key": "replenishment_needed",
                "label": _("Replenishment suggestions"),
                "value": replenishment_count,
                "display_value": f"{replenishment_count:,}",
                "note": _("Reordering rules with a positive quantity to order"),
            },
        ]

        rows = []
        details_limited = False
        warehouse_position_items = []
        warehouse_negative_items = []
        for warehouse in warehouses:
            location_ids = self._ei_internal_location_ids(warehouse)
            warehouse_domain = [
                ("company_id", "=", warehouse.company_id.id),
                ("location_id", "in", location_ids),
            ]
            warehouse_position_count = Quant.search_count(
                warehouse_domain + [("quantity", "!=", 0)]
            )
            warehouse_negative_count = Quant.search_count(
                warehouse_domain + [("quantity", "<", 0)]
            )
            warehouse_position_items.append(
                {
                    "key": warehouse.id,
                    "label": warehouse.name,
                    "value": warehouse_position_count,
                    "display_value": f"{warehouse_position_count:,}",
                }
            )
            warehouse_negative_items.append(
                {
                    "key": warehouse.id,
                    "label": warehouse.name,
                    "value": warehouse_negative_count,
                    "target": warehouse_position_count,
                    "percent": (
                        warehouse_negative_count / warehouse_position_count * 100
                        if warehouse_position_count
                        else 0.0
                    ),
                    "display_value": (
                        f"{warehouse_negative_count:,} / {warehouse_position_count:,}"
                    ),
                    "color": "#e84450",
                }
            )
            groups = Quant.read_group(
                warehouse_domain + [("quantity", "!=", 0)],
                ["product_id", "quantity:sum", "reserved_quantity:sum"],
                ["product_id"],
                limit=self._INVENTORY_DETAIL_LIMIT_PER_WAREHOUSE + 1,
                lazy=False,
            )
            if len(groups) > self._INVENTORY_DETAIL_LIMIT_PER_WAREHOUSE:
                details_limited = True
                groups = groups[: self._INVENTORY_DETAIL_LIMIT_PER_WAREHOUSE]
            product_ids = [group["product_id"][0] for group in groups if group["product_id"]]
            products = {
                product.id: product
                for product in self.env["product.product"].browse(product_ids).exists()
            }
            for group in groups:
                if not group["product_id"]:
                    continue
                product_id, product_name = group["product_id"]
                product = products.get(product_id)
                quantity = group.get("quantity", 0.0)
                reserved = group.get("reserved_quantity", 0.0)
                rows.append(
                    {
                        "key": f"{warehouse.id}-{product_id}",
                        "warehouse": warehouse.name,
                        "product": product_name,
                        "quantity": f"{quantity:,.2f}",
                        "reserved": f"{reserved:,.2f}",
                        "available": f"{quantity - reserved:,.2f}",
                        "uom": product.uom_id.name if product else "",
                    }
                )

        payload = {
            "cards": cards,
            "charts": [
                {
                    "key": "warehouse_stock_positions",
                    "type": "bar",
                    "title": _("Stock positions by warehouse"),
                    "subtitle": _("Exact count of non-zero internal stock quants"),
                    "items": warehouse_position_items,
                },
                {
                    "key": "warehouse_negative_share",
                    "type": "gauge",
                    "title": _("Negative stock share by warehouse"),
                    "items": warehouse_negative_items,
                },
            ],
            "tables": [
                {
                    "key": "current_quantities",
                    "title": _("Current quantities by warehouse and product"),
                    "columns": [
                        {"key": "warehouse", "label": _("Warehouse")},
                        {"key": "product", "label": _("Product")},
                        {"key": "quantity", "label": _("On Hand")},
                        {"key": "reserved", "label": _("Reserved")},
                        {"key": "available", "label": _("Available")},
                        {"key": "uom", "label": _("Unit")},
                    ],
                    "rows": rows,
                }
            ],
            "definitions": {
                "stock_positions": _(
                    "Non-zero stock.quant records in internal locations of the "
                    "permitted warehouses. Quantities with different units are "
                    "never added into one total."
                ),
                "replenishment_needed": _(
                    "Reordering rules whose computed quantity to order is positive."
                ),
            },
            "quality": {
                "detail_limit_per_warehouse": self._INVENTORY_DETAIL_LIMIT_PER_WAREHOUSE,
                "details_limited": details_limited,
            },
        }
        if details_limited:
            payload.update(
                {
                    "status": "limited_detail",
                    "message": _(
                        "Summary counts are exact. The product detail table is limited "
                        "per warehouse for interactive performance."
                    ),
                }
            )
        return payload

    def _ei_internal_location_ids(self, warehouses):
        view_locations = warehouses.mapped("view_location_id")
        if not view_locations:
            return []
        return self.env["stock.location"].search(
            [
                ("id", "child_of", view_locations.ids),
                ("usage", "=", "internal"),
                ("company_id", "in", warehouses.mapped("company_id").ids),
            ]
        ).ids

