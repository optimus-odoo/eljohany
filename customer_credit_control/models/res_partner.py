# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.float_utils import float_compare

class ResPartner(models.Model):
    _inherit = "res.partner"

    x_credit_limit = fields.Monetary(
        string="الحد الائتماني",
        currency_field="company_currency_id",
        help="الحد الأعلى المسموح للرصيد المستحق للعميل (بعملة الشركة).",
    )

    company_currency_id = fields.Many2one(
        "res.currency",
        string="عملة الشركة",
        compute="_compute_company_currency_id",
        store=False,
    )

    x_current_due = fields.Monetary(
        string="الرصيد المستحق الحالي",
        currency_field="company_currency_id",
        compute="_compute_credit_indicators",
        store=False,
    )
    x_credit_available = fields.Monetary(
        string="المتاح من الائتمان",
        currency_field="company_currency_id",
        compute="_compute_credit_indicators",
        store=False,
    )
    x_credit_utilization = fields.Float(
        string="نسبة استخدام الائتمان %",
        compute="_compute_credit_indicators",
        store=False,
    )
    x_is_overdue_followup = fields.Boolean(
        string="عليه فواتير متأخرة",
        compute="_compute_credit_indicators",
        store=False,
    )
    x_is_credit_exceeded = fields.Boolean(
        string="تجاوز الحد الائتماني",
        compute="_compute_credit_indicators",
        store=False,
    )
    # allow_exceed = fields.Boolean(string="سماح يالتجاوز")

    # حقل توافق (Deprecated) لتفادي أخطاء قواعد بيانات قديمة
    # بعض النسخ السابقة كانت تستخدم x_is_credit_expired في Domains/Filters.
    # نُبقيه كحقل مخزن دائمًا False لتفادي:
    # Non-stored field res.partner.x_is_credit_expired cannot be searched
    x_is_credit_expired = fields.Boolean(
        string="(Deprecated) انتهاء ائتمان",
        compute="_compute_x_is_credit_expired",
        store=True,
        readonly=True,
    )

    @api.depends()
    def _compute_x_is_credit_expired(self):
        for rec in self:
            rec.x_is_credit_expired = False

    @api.depends_context("allowed_company_ids")
    def _compute_company_currency_id(self):
        for partner in self:
            partner.company_currency_id = self.env.company.currency_id

    def _status_is_overdue(self, partner):
        status = getattr(partner, "followup_status", False) or getattr(partner, "followup_state", False)
        return status == "with_overdue_invoices"

    def _is_exceeded(self, due, limit, currency):
        if not limit or limit <= 0:
            return False
        return float_compare(due, limit, precision_rounding=currency.rounding) == 1

    @api.depends("credit", "x_credit_limit")
    def _compute_credit_indicators(self):
        currency = self.env.company.currency_id
        for p in self:
            cp = p.commercial_partner_id
            due = cp.credit or 0.0
            limit = cp.x_credit_limit or 0.0

            p.x_current_due = due
            if limit > 0:
                p.x_credit_available = max(limit - due, 0.0)
                p.x_credit_utilization = (due / limit) * 100.0 if limit else 0.0
            else:
                p.x_credit_available = 0.0
                p.x_credit_utilization = 0.0
                
            # if not p.allow_exceed:
            p.x_is_overdue_followup = self._status_is_overdue(cp)
            p.x_is_credit_exceeded = self._is_exceeded(due, limit, currency)

    @api.model
    def get_credit_dashboard_data(self):
        company = self.env.company
        currency = company.currency_id

        domain_customers = [("customer_rank", ">", 0)]
        customers = self.search(domain_customers)
        total_customers = len(customers)

        commercial_ids = list(set(customers.mapped("commercial_partner_id").ids))
        commercial_partners = self.browse(commercial_ids)

        exceeded = 0
        overdue = 0
        both = 0

        items = []
        for cp in commercial_partners:
            due = cp.credit or 0.0
            limit = cp.x_credit_limit or 0.0
            is_overdue = self._status_is_overdue(cp)
            is_exceeded = (limit > 0) and (float_compare(due, limit, precision_rounding=currency.rounding) == 1)
            util = (due / limit) * 100.0 if limit else 0.0

            if is_overdue:
                overdue += 1
            if is_exceeded:
                exceeded += 1
            if is_overdue and is_exceeded:
                both += 1

            items.append((cp, due, limit, is_overdue, is_exceeded, util))

        items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
        top_rows = []
        for cp, due, limit, is_overdue, is_exceeded, util in items_sorted[:10]:
            top_rows.append({
                "id": cp.id,
                "name": cp.display_name,
                "due": currency.round(due),
                "limit": currency.round(limit),
                "overdue": is_overdue,
                "exceeded": is_exceeded,
                "util": round(util, 2),
            })

        buckets = {"0-49": 0, "50-79": 0, "80-99": 0, "100+": 0, "No Limit": 0}
        for cp, due, limit, is_overdue, is_exceeded, util in items:
            if not limit or limit <= 0:
                buckets["No Limit"] += 1
            else:
                if util < 50:
                    buckets["0-49"] += 1
                elif util < 80:
                    buckets["50-79"] += 1
                elif util < 100:
                    buckets["80-99"] += 1
                else:
                    buckets["100+"] += 1

        return {
            "currency": {"name": currency.name, "symbol": currency.symbol},
            "kpis": {
                "total_customers": total_customers,
                "overdue": overdue,
                "exceeded": exceeded,
                "both": both,
            },
            "buckets": buckets,
            "top": top_rows,
        }

    @api.model
    def action_open_overdue_customers(self):
        customers = self.search([("customer_rank", ">", 0)])
        commercial_partners = self.browse(list(set(customers.mapped("commercial_partner_id").ids)))
        ids = [p.id for p in commercial_partners if self._status_is_overdue(p)]
        return {
            "type": "ir.actions.act_window",
            "name": "عملاء لديهم فواتير متأخرة",
            "res_model": "res.partner",
            "view_mode": "tree,kanban,form",
            "domain": [("id", "in", ids)],
            "context": {"search_default_customer": 1},
        }

    @api.model
    def action_open_exceeded_customers(self):
        company = self.env.company
        currency = company.currency_id
        customers = self.search([("customer_rank", ">", 0), ("x_credit_limit", ">", 0)])
        commercial_partners = self.browse(list(set(customers.mapped("commercial_partner_id").ids)))
        ids = []
        for p in commercial_partners:
            due = p.credit or 0.0
            limit = p.x_credit_limit or 0.0
            if limit > 0 and float_compare(due, limit, precision_rounding=currency.rounding) == 1:
                ids.append(p.id)
        return {
            "type": "ir.actions.act_window",
            "name": "عملاء تجاوزوا الحد الائتماني",
            "res_model": "res.partner",
            "view_mode": "tree,kanban,form",
            "domain": [("id", "in", ids)],
            "context": {"search_default_customer": 1},
        }


    # -------- Cleanup legacy domains/filters from older versions --------
    @api.model
    def cleanup_legacy_credit_filters(self):
        """Remove/neutralize legacy filters/actions that reference x_is_credit_expired.

        This avoids: Non-stored field res.partner.x_is_credit_expired cannot be searched
        (in case old saved filters or actions still exist in the database).
        """
        # 1) Saved filters
        filters = self.env["ir.filters"].sudo().search([
            ("model_id", "=", "res.partner"),
            ("domain", "ilike", "x_is_credit_expired"),
        ])
        filters.unlink()

        # 2) Window actions with legacy domain
        actions = self.env["ir.actions.act_window"].sudo().search([
            ("res_model", "=", "res.partner"),
            ("domain", "ilike", "x_is_credit_expired"),
        ])
        actions.write({"domain": "[]"})

        return True
