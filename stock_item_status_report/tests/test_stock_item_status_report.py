from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestStockItemStatusReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].create({"name": "Other Company"})

        ProductTemplate = cls.env["product.template"].sudo()
        company_template = ProductTemplate.create({
            "name": "Selected Company Product",
            "type": "product",
            "company_id": cls.company.id,
        })
        shared_template = ProductTemplate.create({
            "name": "Shared Product",
            "type": "product",
            "company_id": False,
        })
        other_company_template = ProductTemplate.create({
            "name": "Other Company Product",
            "type": "product",
            "company_id": cls.other_company.id,
        })
        cls.company_product = company_template.product_variant_id
        cls.shared_product = shared_template.product_variant_id
        cls.other_company_product = other_company_template.product_variant_id

        cls.vendor_a = cls.env["res.partner"].create({
            "name": "Vendor A",
            "supplier_rank": 1,
        })
        cls.vendor_b = cls.env["res.partner"].create({
            "name": "Vendor B",
            "supplier_rank": 1,
        })

        cls.location = cls.env["stock.location"].sudo().create({
            "name": "Stock Item Status Test Location",
            "usage": "internal",
            "company_id": cls.company.id,
        })

    def _create_wizard(self, products=None):
        values = {
            "company_id": self.company.id,
            "location_ids": [(6, 0, self.location.ids)],
        }
        if products is not None:
            values["product_ids"] = [(6, 0, products.ids)]
        return self.env["stock.item.status.report.wizard"].sudo().create(values)

    def test_get_products_is_limited_to_selected_company(self):
        wizard = self._create_wizard()

        products = wizard.sudo()._get_products()

        self.assertIn(self.company_product, products)
        self.assertIn(self.shared_product, products)
        self.assertNotIn(self.other_company_product, products)

    def test_explicit_selection_cannot_include_another_company(self):
        selected_products = (
            self.company_product
            | self.shared_product
            | self.other_company_product
        )
        wizard = self._create_wizard(selected_products)

        products = wizard.sudo()._get_products()

        self.assertEqual(
            set(products.ids),
            {self.company_product.id, self.shared_product.id},
        )

    def test_vendor_quantities_are_reconciled_to_selected_on_hand(self):
        wizard = self._create_wizard(self.company_product)
        buckets = [
            {
                "vendor_id": self.vendor_a.id,
                "vendor_name": self.vendor_a.display_name,
                "quantity": 8.0,
            },
            {
                "vendor_id": self.vendor_b.id,
                "vendor_name": self.vendor_b.display_name,
                "quantity": 12.0,
            },
        ]

        result = wizard._reconcile_vendor_quantities(
            self.company_product,
            buckets,
            10.0,
        )

        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(sum(item["quantity"] for item in result), 10.0)
        self.assertAlmostEqual(result[0]["quantity"], 4.0)
        self.assertAlmostEqual(result[1]["quantity"], 6.0)

    def test_unattributed_quantity_is_absorbed_by_known_vendor(self):
        wizard = self._create_wizard(self.company_product)
        buckets = [{
            "vendor_id": self.vendor_a.id,
            "vendor_name": self.vendor_a.display_name,
            "quantity": 4.0,
        }]

        result = wizard._reconcile_vendor_quantities(
            self.company_product,
            buckets,
            10.0,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["vendor_id"], self.vendor_a.id)
        self.assertAlmostEqual(result[0]["quantity"], 10.0)

    def test_product_without_vendor_trace_has_empty_vendor(self):
        wizard = self._create_wizard(self.company_product)

        result = wizard._reconcile_vendor_quantities(
            self.company_product,
            [],
            10.0,
        )

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["vendor_id"])
        self.assertEqual(result[0]["vendor_name"], "")
        self.assertAlmostEqual(result[0]["quantity"], 10.0)

    def test_prepare_lines_repeats_product_once_per_vendor(self):
        wizard = self._create_wizard(self.company_product)
        product_id = self.company_product.id
        vendor_qty_map = {
            product_id: [
                {
                    "vendor_id": self.vendor_a.id,
                    "vendor_name": self.vendor_a.display_name,
                    "quantity": 4.0,
                },
                {
                    "vendor_id": self.vendor_b.id,
                    "vendor_name": self.vendor_b.display_name,
                    "quantity": 6.0,
                },
            ],
        }
        model_class = type(wizard)

        with patch.object(
            model_class,
            "_get_products",
            return_value=self.company_product,
        ), patch.object(
            model_class,
            "_get_on_hand_by_product",
            return_value={product_id: 10.0},
        ), patch.object(
            model_class,
            "_get_reorder_point_by_product",
            return_value={},
        ), patch.object(
            model_class,
            "_get_sold_net_from_sale_order",
            return_value={product_id: 0.0},
        ), patch.object(
            model_class,
            "_get_vendor_on_hand_by_product",
            return_value=vendor_qty_map,
        ):
            lines = wizard._prepare_lines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(
            {line["vendor_name"] for line in lines},
            {self.vendor_a.display_name, self.vendor_b.display_name},
        )
        self.assertAlmostEqual(sum(line["qty_on_hand"] for line in lines), 10.0)
