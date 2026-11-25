from odoo.tests.common import TransactionCase
from odoo.tools import float_repr


class TestSaleOrderLineLocationQty(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "edit_sale_order.id_access_create_contact_and_product"
        )
        cls.partner = cls.env["res.partner"].create({"name": "Stock Customer"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Location Quantity Product",
                "default_code": "LOCATION-QTY-TEST",
                "detailed_type": "product",
            }
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.location_1 = cls.env["stock.location"].create(
            {
                "name": "Location 1",
                "location_id": cls.warehouse.lot_stock_id.id,
                "usage": "internal",
                "company_id": cls.env.company.id,
            }
        )
        cls.location_2 = cls.env["stock.location"].create(
            {
                "name": "Location 2",
                "location_id": cls.warehouse.lot_stock_id.id,
                "usage": "internal",
                "company_id": cls.env.company.id,
            }
        )
        cls.other_warehouse = cls.env["stock.warehouse"].create(
            {
                "name": "Other Warehouse",
                "code": "OTHQ",
                "company_id": cls.env.company.id,
            }
        )
        cls.empty_warehouse = cls.env["stock.warehouse"].create(
            {
                "name": "Empty Warehouse",
                "code": "EMPQ",
                "company_id": cls.env.company.id,
            }
        )
        cls.other_company = cls.env["res.company"].sudo().create(
            {"name": "Location Quantity Other Company"}
        )
        cls.other_company_warehouse = cls.env["stock.warehouse"].sudo().create(
            {
                "name": "Other Company Warehouse",
                "code": "OCQW",
                "company_id": cls.other_company.id,
            }
        )
        if "allowed_warehouse_ids" in cls.env.user._fields:
            cls.env.user.allowed_warehouse_ids = [
                (6, 0, [cls.warehouse.id])
            ]
        cls.env["stock.quant"]._update_available_quantity(
            cls.product,
            cls.location_2,
            1.0,
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product,
            cls.other_warehouse.lot_stock_id,
            33.0,
        )
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "warehouse_id": cls.warehouse.id,
            }
        )
        cls.line = cls.env["sale.order.line"].create(
            {
                "order_id": cls.order.id,
                "product_id": cls.product.id,
                "product_uom_qty": 1.0,
            }
        )

    def test_quantity_lists_all_company_warehouses_regardless_of_user_scope(self):
        quantities = {
            warehouse.id: quantity
            for warehouse, quantity in self.line._get_warehouse_quantities()
        }

        self.assertEqual(quantities[self.warehouse.id], 1.0)
        self.assertEqual(quantities[self.other_warehouse.id], 33.0)
        self.assertEqual(quantities[self.empty_warehouse.id], 0.0)
        self.assertNotIn(self.other_company_warehouse.id, quantities)

    def test_html_includes_all_warehouses_and_zero_quantities_by_default(self):
        self.line._compute_location_qty()
        location_qty = str(self.line.location_qty)
        precision_digits = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )

        self.assertIn(self.warehouse.display_name, location_qty)
        self.assertIn(self.other_warehouse.display_name, location_qty)
        self.assertIn(self.empty_warehouse.display_name, location_qty)
        self.assertNotIn(self.other_company_warehouse.display_name, location_qty)
        self.assertIn(float_repr(1.0, precision_digits), location_qty)
        self.assertIn(float_repr(33.0, precision_digits), location_qty)
        self.assertIn(float_repr(0.0, precision_digits), location_qty)

    def test_warehouse_change_keeps_all_company_warehouses_visible(self):
        self.order.warehouse_id = self.other_warehouse
        self.line._compute_location_qty()
        location_qty = str(self.line.location_qty)

        self.assertIn(self.other_warehouse.display_name, location_qty)
        self.assertIn(self.warehouse.display_name, location_qty)
        self.assertIn(self.empty_warehouse.display_name, location_qty)

    def test_location_quantity_is_recomputed_after_stock_change(self):
        self.line._compute_location_qty()
        self.env["stock.quant"]._update_available_quantity(
            self.product,
            self.location_2,
            2.0,
        )
        self.line.invalidate_recordset(["location_qty"])
        precision_digits = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )

        reloaded_value = str(
            self.env["sale.order.line"].browse(self.line.id).location_qty
        )

        self.assertIn(self.warehouse.display_name, reloaded_value)
        self.assertIn(self.other_warehouse.display_name, reloaded_value)
        self.assertIn(self.empty_warehouse.display_name, reloaded_value)
        self.assertIn(float_repr(3.0, precision_digits), reloaded_value)
