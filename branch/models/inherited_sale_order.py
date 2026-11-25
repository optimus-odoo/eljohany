# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _get_active_branch_id(self):
        branch_id = self.env.context.get('branch_id')
        allowed_branch_ids = self.env.context.get('allowed_branch_ids') or []
        if not branch_id and allowed_branch_ids:
            if isinstance(allowed_branch_ids, int):
                branch_id = allowed_branch_ids
            elif isinstance(allowed_branch_ids, str):
                branch_id = allowed_branch_ids.split(',')[0]
            else:
                branch_id = allowed_branch_ids[0]
        if not branch_id and self.env.user.branch_id:
            branch_id = self.env.user.branch_id.id
        if branch_id:
            branch_id = int(branch_id)
        return branch_id or False

    @api.model
    def _get_branch_warehouse_id(self, branch_id, company_id=False):
        if not branch_id:
            return False
        domain = [('branch_id', '=', branch_id)]
        company_id = company_id or self.env.company.id
        if company_id:
            domain.append(('company_id', '=', company_id))
        warehouse = self.env['stock.warehouse'].search(domain, limit=1)
        return warehouse.id or False

    @api.model
    def default_get(self, fields):
        res = super(SaleOrder, self).default_get(fields)
        branch_id = self._get_active_branch_id()
        warehouse_id = self._get_branch_warehouse_id(
            branch_id,
            res.get('company_id') or self.env.company.id,
        )

        if 'branch_id' in fields:
            res.update({
                'branch_id': branch_id,
            })
        if 'warehouse_id' in fields and warehouse_id:
            res.update({
                'warehouse_id': warehouse_id,
            })

        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            branch_id = vals.get('branch_id') or self._get_active_branch_id()
            if branch_id:
                vals.setdefault('branch_id', branch_id)
                warehouse_id = self._get_branch_warehouse_id(
                    branch_id,
                    vals.get('company_id') or self.env.company.id,
                )
                if warehouse_id:
                    vals.setdefault('warehouse_id', warehouse_id)
        return super(SaleOrder, self).create(vals_list)

    branch_id = fields.Many2one('res.branch', string="Branch")

    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res['branch_id'] = self.branch_id.id
        return res

    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        if self.state != 'draft':
            raise UserError(
                _("You can only change the branch when the Sale Order is in draft state."))

        selected_branch = self.branch_id
        user = self.env.user

        if selected_branch:
            if user.has_group('branch.group_multi_branch'):
                allowed_branch_ids = self.env.context.get(
                    'allowed_branch_ids', [])
                if selected_branch.id not in allowed_branch_ids:
                    raise UserError(_(
                        "Please select an active branch only. Other branches may cause data inconsistency.\n\n"
                        "If you wish to work in another branch, switch to it using the top-right menu."
                    ))
            else:
                if selected_branch != user.branch_id:
                    raise UserError(_(
                        "You are not allowed to switch branches.\n\n"
                        "Please use your assigned branch or contact an administrator."
                    ))
