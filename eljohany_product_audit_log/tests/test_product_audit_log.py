from odoo.exceptions import AccessError
from odoo.modules.module import get_module_resource
from odoo.tests.common import TransactionCase
from odoo.tools.translate import TranslationFileReader


class TestProductAuditLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.audit_group = cls.env.ref(
            "eljohany_product_audit_log.group_product_audit_viewer"
        )
        cls.product = cls.env["product.template"].create(
            {"name": "Audited Product", "list_price": 100.0}
        )
        cls.writer = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Product Audit Writer",
                "login": "product.audit.writer",
                "email": "product.audit.writer@example.com",
                "groups_id": [
                    (6, 0, [cls.env.ref("base.group_user").id, cls.audit_group.id])
                ],
            }
        )
        edit_group = cls.env.ref(
            "edit_sale_order.id_access_create_contact_and_product",
            raise_if_not_found=False,
        )
        if edit_group:
            cls.writer.groups_id |= edit_group

    def test_product_write_creates_detailed_log(self):
        self.product.with_user(self.writer).write({"list_price": 125.5})

        log = self.product.change_log_ids.filtered(
            lambda line: line.field_name == "list_price"
        )
        self.assertEqual(len(log), 1)
        self.assertEqual(log.changed_by_id, self.writer)
        self.assertEqual(log.old_value, "100.0")
        self.assertEqual(log.new_value, "125.5")
        self.assertEqual(log.target_model, "product.template")
        self.assertTrue(log.field_display_name)

    def test_unchanged_value_is_not_logged(self):
        initial_count = len(self.product.change_log_ids)
        self.product.with_user(self.writer).write({"list_price": 100.0})
        self.assertEqual(len(self.product.change_log_ids), initial_count)

    def test_variant_write_is_visible_on_product_log(self):
        variant = self.product.product_variant_id
        variant.with_user(self.writer).write({"barcode": "AUDIT-001"})

        log = self.product.change_log_ids.filtered(
            lambda line: line.field_name == "barcode"
        )
        self.assertEqual(len(log), 1)
        self.assertEqual(log.product_id, variant)
        self.assertEqual(log.target_model, "product.product")
        self.assertEqual(log.new_value, "AUDIT-001")

    def test_log_is_immutable(self):
        self.product.with_user(self.writer).write({"list_price": 110.0})
        log = self.product.change_log_ids[:1]
        with self.assertRaises(AccessError):
            log.write({"new_value": "Tampered"})
        with self.assertRaises(AccessError):
            log.unlink()

    def test_user_without_group_cannot_read_logs(self):
        self.product.with_user(self.writer).write({"list_price": 110.0})
        user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Product User Without Audit Access",
                "login": "product.no.audit",
                "email": "product.no.audit@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        with self.assertRaises(AccessError):
            self.product.change_log_ids.with_user(user).read(["field_name"])

    def test_arabic_translation_file_is_loadable(self):
        translation_path = get_module_resource(
            "eljohany_product_audit_log",
            "i18n",
            "ar_001.po",
        )
        rows = list(TranslationFileReader(translation_path))
        translations = {
            row["src"]: row["value"]
            for row in rows
            if row.get("src") and row.get("value")
        }

        self.assertGreaterEqual(len(rows), 29)
        self.assertEqual(translations["Change Log"], "سجل التغييرات")
        self.assertEqual(translations["Changed By"], "تم التعديل بواسطة")
        self.assertEqual(translations["Change Date"], "تاريخ التعديل")
        self.assertEqual(translations["Previous Value"], "القيمة السابقة")
        self.assertEqual(translations["New Value"], "القيمة الجديدة")
