{
    "name": "Sale Allowed Warehouses by User",
    "version": "17.0.2.0.1",
    "license": "LGPL-3",
    "category": "Sales",
    "summary": "Sale Order warehouse domain based on user's allowed warehouses (allowed_journal_ids style).",
    "depends": ["sale", "stock", "sale_stock", "eq_saleline_stock_location"],
    "data": [
        "views/res_users_view.xml",
        "views/sale_order_view.xml"
    ],
    "installable": True,
    "application": False
}
