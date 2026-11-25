from odoo import models, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        domain = domain or []
        
        if self.env.su or self._context.get('skip_company_filter'):
            return super()._search(
                domain, 
                offset=offset, 
                limit=limit, 
                order=order, 
                access_rights_uid=access_rights_uid
            )
        
        allowed_companies = self.env.companies.ids
        
        has_company_8 = 8 in allowed_companies
        other_companies = [cid for cid in allowed_companies if cid != 8]
        
        if has_company_8 and other_companies:
            domain = domain + ['|', ('company_id', '=', 8), ('company_id', '=', False)]
        elif has_company_8:
            domain = domain + [('company_id', '=', 8)]
        elif other_companies:
            domain = domain + ['|', ('company_id', '=', False), ('company_id', 'in', allowed_companies)]
        
        return super()._search(
            domain, 
            offset=offset, 
            limit=limit, 
            order=order, 
            access_rights_uid=access_rights_uid
        )

    @api.model_create_multi
    def create(self, vals_list):
        return super(ProductTemplate, self.with_context(skip_company_filter=True)).create(vals_list)

    def write(self, vals):
        return super(ProductTemplate, self.with_context(skip_company_filter=True)).write(vals)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        """Override search to apply company-specific filtering"""
        domain = domain or []
        
        if self.env.su or self._context.get('skip_company_filter'):
            return super()._search(
                domain, 
                offset=offset, 
                limit=limit, 
                order=order, 
                access_rights_uid=access_rights_uid
            )
        
        allowed_companies = self.env.companies.ids
        
        has_company_8 = 8 in allowed_companies
        other_companies = [cid for cid in allowed_companies if cid != 8]
        
        if has_company_8 and other_companies:
            domain = domain + ['|', ('company_id', '=', 8), ('company_id', '=', False)]
        elif has_company_8:
            domain = domain + [('company_id', '=', 8)]
        elif other_companies:
            domain = domain + ['|', ('company_id', '=', False), ('company_id', 'in', allowed_companies)]
        
        return super()._search(
            domain, 
            offset=offset, 
            limit=limit, 
            order=order, 
            access_rights_uid=access_rights_uid
        )

    @api.model_create_multi
    def create(self, vals_list):
        return super(ProductProduct, self.with_context(skip_company_filter=True)).create(vals_list)

    def write(self, vals):
        return super(ProductProduct, self.with_context(skip_company_filter=True)).write(vals)