# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import uuid
import json
from markupsafe import Markup, escape
from odoo import _, fields, models, api
from odoo.tools import float_repr
from odoo.tools.float_utils import float_compare
from datetime import datetime
from base64 import b64decode, b64encode
from lxml import etree
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_der_x509_certificate

MAX_SALES_DISCOUNT = 3.0
DISCOUNT_LIMIT_OVERRIDE_GROUP = 'edit_sale_order.group_allow_override_discount_limit'
PRICE_UNIT_COST_FLOOR_OVERRIDE_GROUP = 'edit_sale_order.group_allow_sale_below_cost'


def _is_discount_over_limit(discount):
    return float_compare(discount or 0.0, MAX_SALES_DISCOUNT, precision_digits=2) > 0


def _can_override_discount_limit(env):
    return env.user.has_group(DISCOUNT_LIMIT_OVERRIDE_GROUP)


def _can_override_price_unit_cost_floor(env):
    return env.user.has_group(PRICE_UNIT_COST_FLOOR_OVERRIDE_GROUP)


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    so_default = fields.Boolean(string="", )


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Keep the standard fields optional.  Requiring them at model level makes
    # Odoo try to add NOT NULL constraints to existing production data during
    # every registry update, which fails while legacy/shared records are empty.
    phone = fields.Char(required=False, copy=False)
    vat = fields.Char(string='Tax ID', copy=False, index=True,
                      help="The Tax Identification Number. Values here will be validated based on the country format. You can use '/' to indicate that the partner is not subject to tax.")
    plumber_id = fields.Many2one(comodel_name="plumber.plumber", string='Plumber/السباك')
    company_id = fields.Many2one('res.company', 'Company', index=True, required=False)


    @api.model
    def default_get(self, fields):
        result = super(ResPartner, self).default_get(fields)
        payment = self.env["account.payment.term"].search([("so_default", "=", True)], limit=1)
        if 'property_payment_term_id' in fields and payment:
            result['property_payment_term_id'] = payment.id
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            # Be sure name_search is symetric to display_name
            name = name.split(' / ')[-1]
            domain = ['|', '|', '|', ('ref', operator, name), ('mobile', operator, name), ('phone', operator, name),
                      ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    # @api.constrains('vat', 'company_id')
    # def constrain_vat(self):
    #     for rec in self:
    #         if rec.vat and rec.company_id:
    #             duplicates = self.env['res.partner'].sudo().search([
    #                 ('vat', '=', rec.vat),
    #                 ('company_id', '=', rec.company_id.id),
    #                 ('id', '!=', rec.id)
    #             ], limit=1)
    #             if duplicates:
    #                 print(duplicates.name)
    #                 raise ValidationError(_("A contact with the same VAT number already exists in this company."))
    @api.model_create_multi
    def create(self, vals_list):
        records = super(ResPartner, self).create(vals_list)
        if self.user_has_groups('edit_sale_order.id_access_create_contact_and_product'):
            return records
        else:
            raise UserError(_("You do not have the required permissions to create a Contact."))

    def write(self, vals):
        restricted_fields = ['name', 'email', 'phone', 'mobile', 'ref', 'vat']
        if any(field in vals for field in restricted_fields) and not self.user_has_groups(
                'edit_sale_order.id_access_create_contact_and_product'):
            raise UserError(_("You do not have the required permissions to Edit Contact details."))

        return super(ResPartner, self).write(vals)


class ProjectProjectNew(models.Model):
    _name = 'projects.project'
    _description = 'Project'

    name = fields.Char(required=True)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    phone = fields.Char(copy=False, related="partner_id.phone")
    customer_code = fields.Char(copy=False, related="partner_id.ref")
    total_discount_amount = fields.Float(compute="_compute_sum_discount_amount")
    total_before_discount = fields.Float(compute="_compute_sum_discount_amount")
    projects_id = fields.Many2one(comodel_name="projects.project", string='المشروع')
    plumber_id = fields.Many2one(comodel_name="plumber.plumber", related="partner_id.plumber_id", string='Plumber/السباك')

    @api.depends('order_line')
    def _compute_sum_discount_amount(self):
        for rec in self:
            rec.total_discount_amount = sum(rec.order_line.mapped("discount_amount"))
            rec.total_before_discount = sum(line.price_unit * line.product_uom_qty for line in rec.order_line)

    def default_payment_term(self):
        payment = self.env["account.payment.term"].search([("so_default", "=", True)], limit=1)
        if payment:
            return payment

    payment_term_id = fields.Many2one(
        comodel_name='account.payment.term',
        string="Payment Terms",
        default=default_payment_term,
        store=True, readonly=False, check_company=True,  # Unrequired company
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        values['projects_id'] = self.projects_id.id
        values['plumber_id'] = self.plumber_id.id
        return values

    def _check_discount_limit(self):
        if _can_override_discount_limit(self.env):
            return
        for order in self:
            line = order.order_line.filtered(
                lambda rec: not rec.display_type and _is_discount_over_limit(rec.discount)
            )[:1]
            if line:
                raise ValidationError(_(
                    "Discount cannot exceed %(limit)s%% on quotation/sales order lines."
                ) % {"limit": MAX_SALES_DISCOUNT})

    @api.constrains("order_line", "currency_id", "company_id", "date_order")
    def _check_order_line_price_unit_cost_floor(self):
        self.order_line._check_price_unit_not_below_product_cost()

    def action_confirm(self):
        self._check_discount_limit()
        self.order_line.with_context(
            active_model="sale.order",
            check_sale_price_unit_cost_floor=True,
        )._check_price_unit_not_below_product_cost()
        return super().action_confirm()


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    default_code = fields.Char(required=False, related="product_tmpl_id.default_code")


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    cost = fields.Float(string="", required=False, store=True)
    location_qty = fields.Html(
        string="Location Qty",
        compute="_compute_location_qty",
        store=False,
        readonly=True,
    )
    available_stock_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_available_stock_location_ids",
        store=False,
    )
    discount_amount = fields.Float()
    internal_reference = fields.Char(required=False, string="Internal Reference",
                                     related="product_template_id.default_code")

    def _get_product_cost_in_order_currency(self):
        self.ensure_one()
        product = self.product_id
        if not product:
            return 0.0

        order = self.order_id
        company = order.company_id or self.env.company
        product = product.with_company(company).sudo()
        cost = product.standard_price or 0.0

        if self.product_uom and product.uom_id and self.product_uom != product.uom_id:
            cost = product.uom_id._compute_price(cost, self.product_uom)

        order_currency = order.currency_id or company.currency_id
        company_currency = company.currency_id
        if order_currency and company_currency and order_currency != company_currency:
            conversion_date = (
                fields.Date.to_date(order.date_order)
                if order.date_order
                else fields.Date.context_today(self)
            )
            cost = company_currency._convert(cost, order_currency, company, conversion_date)

        return cost

    def _get_minimum_allowed_unit_price(self):
        self.ensure_one()
        return max(
            self._get_product_cost_in_order_currency(),
            self.purchase_price or 0.0,
        )

    def _get_price_below_cost_message(self):
        self.ensure_one()
        return _(
            "Unit price cannot be less than product cost or purchase price.\n"
            "Product: %(product)s\n"
            "Please increase the unit price before saving or confirming the order."
        ) % {
            "product": self.product_id.display_name,
        }

    def _should_check_price_unit_product_cost_floor(self):
        self.ensure_one()
        if _can_override_price_unit_cost_floor(self.env):
            return False
        if self.env.context.get("active_model") != "sale.order":
            return False
        if self.env.context.get("check_sale_price_unit_cost_floor"):
            return True
        return self.order_id.state in ("sale", "done")

    def _is_price_unit_below_product_cost(self):
        self.ensure_one()
        if (
            self.display_type
            or not self.product_id
            or not self._should_check_price_unit_product_cost_floor()
        ):
            return False
        minimum_price = self._get_minimum_allowed_unit_price()
        if minimum_price <= 0.0:
            return False
        currency = (
            self.order_id.currency_id
            or self.order_id.company_id.currency_id
            or self.env.company.currency_id
        )
        return float_compare(
            self.price_unit or 0.0,
            minimum_price,
            precision_rounding=currency.rounding if currency else 0.01,
        ) < 0

    def _check_price_unit_not_below_product_cost(self):
        for line in self:
            if line._is_price_unit_below_product_cost():
                raise ValidationError(line._get_price_below_cost_message())

    @api.onchange(
        "product_id",
        "product_template_id",
        "product_uom",
        "order_id.currency_id",
        "order_id.company_id",
    )
    def _onchange_price_unit_product_cost_floor(self):
        for line in self:
            if line._is_price_unit_below_product_cost():
                line.price_unit = line._get_minimum_allowed_unit_price()

    @api.constrains("price_unit", "purchase_price", "product_id", "product_uom", "display_type")
    def _check_price_unit_product_cost_floor(self):
        self._check_price_unit_not_below_product_cost()

    @api.depends("order_id.company_id", "order_id.warehouse_id")
    def _compute_available_stock_location_ids(self):
        Location = self.env["stock.location"]
        user = self.env.user
        has_allowed_warehouses = "allowed_warehouse_ids" in user._fields
        for line in self:
            company = line.order_id.company_id
            domain = [("usage", "=", "internal")]
            if company:
                domain += ["|", ("company_id", "=", company.id), ("company_id", "=", False)]
            if has_allowed_warehouses and user.allowed_warehouse_ids:
                warehouses = user.allowed_warehouse_ids
                if company:
                    warehouses = warehouses.filtered(lambda warehouse: warehouse.company_id == company)
                domain.append(("warehouse_id", "in", warehouses.ids))
            elif line.order_id.warehouse_id:
                domain.append(("id", "child_of", line.order_id.warehouse_id.view_location_id.id))
            line.available_stock_location_ids = Location.search(domain)

    @api.onchange("discount_amount", "price_unit", "product_uom_qty", "product_template_id")
    def _compute_discount(self):
        warning = False
        for rec in self:
            total_price = rec.price_unit * rec.product_uom_qty
            if total_price > 0:
                discount = (rec.discount_amount / total_price) * 100
                if not _can_override_discount_limit(rec.env) and _is_discount_over_limit(discount):
                    discount = MAX_SALES_DISCOUNT
                    rec.discount_amount = total_price * MAX_SALES_DISCOUNT / 100.0
                    warning = rec._get_discount_limit_warning()
                rec.discount = discount
        if warning:
            return warning

    @api.onchange("discount")
    def _compute_discount_percentage(self):
        warning = False
        for rec in self:
            if not _can_override_discount_limit(rec.env) and _is_discount_over_limit(rec.discount):
                rec.discount = MAX_SALES_DISCOUNT
                warning = rec._get_discount_limit_warning()
            total_price = rec.price_unit * rec.product_uom_qty
            if total_price > 0:
                rec.discount_amount = (rec.discount / 100) * total_price
            else:
                rec.discount_amount = 0
        if warning:
            return warning

    def _get_discount_limit_warning(self):
        return {
            "warning": {
                "title": _("Discount Limit"),
                "message": _("Discount cannot exceed %(limit)s%%.") % {
                    "limit": MAX_SALES_DISCOUNT,
                },
            }
        }

    @api.constrains("discount")
    def _check_discount_limit(self):
        if _can_override_discount_limit(self.env):
            return
        for rec in self:
            if not rec.display_type and _is_discount_over_limit(rec.discount):
                raise ValidationError(_(
                    "Discount cannot exceed %(limit)s%% on quotation/sales order lines."
                ) % {"limit": MAX_SALES_DISCOUNT})

    def _get_warehouse_quantities(self):
        """Return physical on-hand quantity for every company warehouse."""
        self.ensure_one()
        if not self.product_id:
            return []

        company = self.order_id.company_id or self.env.company
        warehouses = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", company.id)],
            order="sequence, id",
        )

        quantities_by_warehouse = {warehouse.id: 0.0 for warehouse in warehouses}
        if warehouses:
            # This is an explicitly read-only company-wide display.  Sudo is
            # intentionally scoped by both company and warehouse so warehouse
            # operation restrictions do not hide quantities from this field.
            quantities_by_location = self.env["stock.quant"].sudo()._read_group(
                [
                    ("product_id", "=", self.product_id.id),
                    ("location_id.usage", "=", "internal"),
                    ("location_id.warehouse_id", "in", warehouses.ids),
                    ("company_id", "=", company.id),
                ],
                ["location_id"],
                ["quantity:sum"],
            )
            for location, quantity in quantities_by_location:
                warehouse_id = location.warehouse_id.id
                if warehouse_id in quantities_by_warehouse:
                    quantities_by_warehouse[warehouse_id] += quantity

        return [
            (warehouse, quantities_by_warehouse[warehouse.id])
            for warehouse in warehouses
        ]

    @api.depends(
        "product_id",
        "order_id.company_id",
    )
    def _compute_location_qty(self):
        precision_digits = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for line in self:
            rows = []
            for warehouse, quantity in line._get_warehouse_quantities():
                rows.append(
                    Markup(
                        "<p><b>📍 {}:</b> "
                        "<span style='color:blue;'>{}</span></p>"
                    ).format(
                        escape(warehouse.display_name),
                        escape(float_repr(quantity, precision_digits)),
                    )
                )
            line.location_qty = Markup("").join(rows)

    @api.constrains('product_template_id', 'product_uom_qty', "qty_invoiced", "qty_delivered", "purchase_price")
    def get_cost(self):
        for rec in self:
            rec.cost = (rec.qty_invoiced - rec.qty_delivered) * rec.purchase_price


class SaleReport(models.Model):
    _inherit = "sale.report"

    cost = fields.Float(string="", required=False, )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['cost'] = f"""SUM(l.cost)
            """
        return res


class AccountMove(models.Model):
    _inherit = 'account.move'
    projects_id = fields.Many2one(comodel_name="projects.project", string='المشروع')

    def _check_discount_limit(self):
        if _can_override_discount_limit(self.env):
            return
        sales_moves = self.filtered(lambda rec: rec.move_type in ('out_invoice', 'out_refund', 'out_receipt'))
        for move in sales_moves:
            line = move.invoice_line_ids.filtered(
                lambda rec: not rec.display_type and _is_discount_over_limit(rec.discount)
            )[:1]
            if line:
                raise ValidationError(_(
                    "Discount cannot exceed %(limit)s%% on sales invoice lines."
                ) % {"limit": MAX_SALES_DISCOUNT})

    def action_post(self):
        self._check_discount_limit()
        return super().action_post()
    
    @api.depends('amount_total_signed', 'amount_tax_signed', 'l10n_sa_confirmation_datetime', 'company_id', 'company_id.vat')
    def _compute_qr_code_str(self):
        """ Generate the qr code for Saudi e-invoicing. Specs are available at the following link at page 23
        https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20210528_ZATCA_Electronic_Invoice_Security_Features_Implementation_Standards_vShared.pdf
        """
        def get_qr_encoding(tag, field):
            company_name_byte_array = field.encode()
            company_name_tag_encoding = tag.to_bytes(length=1, byteorder='big')
            company_name_length_encoding = len(company_name_byte_array).to_bytes(length=1, byteorder='big')
            return company_name_tag_encoding + company_name_length_encoding + company_name_byte_array

        for record in self:
            qr_code_str = ''
            if record.l10n_sa_confirmation_datetime and record.company_id.vat:
                seller_name_enc = get_qr_encoding(1, "شركة محمد سليمان عبدالله الجهني التجارية شركة شخص واحد")
                company_vat_enc = get_qr_encoding(2, record.company_id.vat)
                time_sa = fields.Datetime.context_timestamp(self.with_context(tz='Asia/Riyadh'), record.l10n_sa_confirmation_datetime)
                timestamp_enc = get_qr_encoding(3, time_sa.strftime(self._get_iso_format_asia_riyadh_date('T')))
                totals = record._get_l10n_sa_totals()
                invoice_total_enc = get_qr_encoding(4, float_repr(abs(totals['total_amount']), 2))
                total_vat_enc = get_qr_encoding(5, float_repr(abs(totals['total_tax']), 2))

                str_to_encode = seller_name_enc + company_vat_enc + timestamp_enc + invoice_total_enc + total_vat_enc
                qr_code_str = b64encode(str_to_encode).decode()
            record.l10n_sa_qr_code_str = qr_code_str

    

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange("discount")
    def _onchange_discount_limit(self):
        warning = False
        for rec in self:
            if (
                rec.move_id.move_type in ('out_invoice', 'out_refund', 'out_receipt')
                and not _can_override_discount_limit(rec.env)
                and _is_discount_over_limit(rec.discount)
            ):
                rec.discount = MAX_SALES_DISCOUNT
                warning = {
                    "warning": {
                        "title": _("Discount Limit"),
                        "message": _("Discount cannot exceed %(limit)s%%.") % {
                            "limit": MAX_SALES_DISCOUNT,
                        },
                    }
                }
        if warning:
            return warning

    @api.constrains("discount", "move_id", "display_type")
    def _check_discount_limit(self):
        if _can_override_discount_limit(self.env):
            return
        for rec in self:
            if (
                rec.move_id.move_type in ('out_invoice', 'out_refund', 'out_receipt')
                and not rec.display_type
                and _is_discount_over_limit(rec.discount)
            ):
                raise ValidationError(_(
                    "Discount cannot exceed %(limit)s%% on sales invoice lines."
                ) % {"limit": MAX_SALES_DISCOUNT})


class ProductTemplateINh(models.Model):
    _inherit = 'product.template'

    # display_name = fields.Char(string="Display Name", compute="_compute_display_name", store=True)
    # Shared products intentionally have no company in standard Odoo.
    company_id = fields.Many2one('res.company', 'Company', index=True, required=False)


    # @api.depends('name')
    # def _compute_display_name(self):
    #     for rec in self:
    #         rec.display_name = str(rec.name)

    @api.constrains("default_code", "company_id")
    def _check_unique_default_code(self):
        for product in self:
            if product.default_code:
                domain = [
                    ("default_code", "=", product.default_code),
                    ("company_id", "=", product.company_id.id),
                    ("id", "!=", product.id),  # Exclude the current record
                ]
                if self.env["product.template"].sudo().search_count(domain):
                    raise UserError(_("A product with the same Internal Reference and Company already exists."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super(ProductTemplateINh, self).create(vals_list)
        if self.user_has_groups('edit_sale_order.id_access_create_contact_and_product'):
            return records
        else:
            raise UserError(_("You do not have the required permissions to create a product."))


    def write(self, vals):
        restricted_fields = ['name', 'display_name', 'default_code', 'sale_ok', 'purchase_ok', 'description', 'description_sale', 'description_purchase', 'categ_id', 'list_price', 'standard_price', 'uom_id', 'taxes_id', 'detailed_type', 'invoice_policy', 'tracking']
        if any(field in vals for field in restricted_fields) and not self.user_has_groups(
                'edit_sale_order.id_access_create_contact_and_product'):
            raise UserError(_("You do not have the required permissions to Edit product."))

        return super(ProductTemplateINh, self).write(vals)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        restricted_fields = ['name', 'display_name', 'default_code', 'sale_ok', 'purchase_ok', 'description', 'description_sale', 'description_purchase', 'categ_id', 'list_price', 'standard_price', 'uom_id', 'taxes_id', 'detailed_type', 'invoice_policy', 'tracking']
        if any(field in vals for field in restricted_fields) and not self.user_has_groups(
                'edit_sale_order.id_access_create_contact_and_product'):
            raise UserError(_("You do not have the required permissions to Edit product."))

        return super(ProductProduct, self).write(vals)
        
    # display_name = fields.Char(string="Display Name", compute="_compute_display_name", store=True)

    # @api.depends('name')
    # def _compute_display_name(self):
    #     for rec in self:
    #         rec.display_name = str(rec.name)


class PlumberPlumber(models.Model):
    _name = 'plumber.plumber'
    _description = 'New Plumber'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    display_name = fields.Char(required=False, compute="_compute_display_name")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = str(rec.code) + " - " + str(rec.name)


class PaymentRegisterForm(models.TransientModel):
    _inherit = 'account.payment.register'

    plumber_id = fields.Many2one(comodel_name="plumber.plumber", string="Plumper/سباك")

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super(PaymentRegisterForm, self)._create_payment_vals_from_wizard(batch_result)
        payment_vals['plumber_id'] = self.plumber_id.id
        return payment_vals


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    plumber_id = fields.Many2one(comodel_name="plumber.plumber", string="Plumper/سباك")
