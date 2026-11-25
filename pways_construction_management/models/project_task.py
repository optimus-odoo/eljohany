from odoo import models, fields, api , _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, date

class ProjectTask(models.Model):
    _inherit = 'project.task'

    all_bills_count = fields.Integer(compute='_compute_all_bills_count')
    stock_moves_count = fields.Integer(compute='total_stock_moves_count')
    material_reqsn_count = fields.Integer(compute='_compute_material_reqsn_count')
    material_reqsn_scrap_count = fields.Integer(compute='_compute_material_scrap_reqsn_count')
    material_reqsn_internal_count = fields.Integer(compute='_compute_material_internal_reqsn_count')
    stock_count = fields.Integer(compute='_compute_stock_count')
    picking_count = fields.Integer(compute='_compute_picking_count')
    job_cost_id = fields.Many2one('job.costing', string='Job Cost Center',)
    parent_task_id = fields.Many2one('project.task', string='Project Parent Task')
    process_id = fields.Many2one('construct.process', string='Process')
    move_ids = fields.Many2many('material.purchase.requisition.line',compute='_compute_stock_picking_moves',store=True,)
    job_cost_ids = fields.One2many('job.costing','task_id',)
    picking_ids = fields.One2many('material.purchase.requisition','task_id',string='Stock Pickings')
    material_plan_ids = fields.One2many('material.plan','material_task_id',string='Material Plannings')
    consumed_material_ids = fields.One2many('consumed.material','consumed_task_material_id',string='Consumed Materials')
    child_task_ids = fields.One2many('project.task', 'parent_task_id', string='Child Tasks')
    job_number = fields.Char(string = "Job Number",copy = False,)
    expense_ids = fields.One2many('hr.expense', 'task_id', string="Expense")
    req_vehcle_line_ids = fields.One2many('vehicle.equipment.request', 'task_id', string='Vehicle', copy=False, domain=[('request_type','=','vehicle')], )
    req_equipment_line_ids = fields.One2many('vehicle.equipment.request', 'task_id', string='Equipment', copy=False, domain=[('request_type','=','equipment')], )
    instruct_qlty_ids = fields.One2many('construct.instruction.qlty.checklist', 'task_id')
    stock_picking_ids = fields.One2many('stock.picking', 'task_id')
    progress_bar = fields.Float(string='Progress Bar', help='Calculate the progress of the task ' 'based on the task stage', compute='_compute_task__progress_bar')
    stage_is_progress = fields.Boolean(related='stage_id.is_progress_stage', help='Status of the task based the ' 'stage')
    task_document_ids = fields.One2many('construct.attachment.documents', 'task_id', string="Documents")

    ###### Compute methods ######

    @api.depends('stage_id')
    def _compute_task__progress_bar(self):
        for rec in self:
            rec.progress_bar = rec.stage_id.progress_bar

    @api.depends('picking_ids.requisition_line_ids')
    def _compute_stock_picking_moves(self):
        for rec in self:
            rec.ensure_one()
            rec.move_ids = self.env['material.purchase.requisition.line']
            for picking in rec.picking_ids:
                rec.move_ids = picking.requisition_line_ids.ids

    def _compute_picking_count(self):
        picking = self.env['stock.picking']
        for task in self:
            task.picking_count = picking.search_count([('task_id', '=', self.id)])
    
    def _compute_all_bills_count(self):
        bill_obj = self.env['account.move']
        for project in self:
            project.all_bills_count = bill_obj.search_count([('task_id.id', '=', self.id)])
            
    def total_stock_moves_count(self):
        for task in self:
            task.stock_moves_count = len(task.stock_picking_ids.ids)

    def _compute_material_reqsn_count(self):
        boq = self.env['material.purchase.requisition']
        for project in self:
            project.material_reqsn_count = boq.search_count([('task_id', '=', self.id), ('requisition_type', '=', 'purchase')])

    def _compute_material_scrap_reqsn_count(self):
        boq = self.env['material.purchase.requisition']
        for project in self:
            project.material_reqsn_scrap_count = boq.search_count([('task_id', '=', self.id), ('requisition_type', '=', 'scrap')])
    
    def _compute_material_internal_reqsn_count(self):
        boq = self.env['material.purchase.requisition']
        for project in self:
            project.material_reqsn_internal_count = boq.search_count([('task_id', '=', self.id), ('requisition_type', '=', 'internal')])
    
    def _compute_stock_count(self):
        material_plan_ids = self.material_plan_ids.mapped('product_id')
        boq = self.env['product.product']
        self.stock_count = boq.search_count([('id', 'in', material_plan_ids.ids)])

    ###### state button methods ######

    def material_reqsn_action(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pways_construction_management.action_material_purchase_requisition")
        action['domain'] = [('task_id', '=', self.id), ('requisition_type', '=', 'purchase')]
        action['context'] = {
            'default_project_id': self.project_id.id,
            'default_task_id': self.id,
            'default_task_user_ids': self.user_ids.ids,
            'default_job_cost_id': self.job_cost_id.id,
            'default_analytic_account_id': self.analytic_account_id.id,
            'default_requisition_type': 'purchase',
        }        
        return action

    def material_reqsn_scrap_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Scrap/Store',
            'res_model': 'material.purchase.requisition',
            'domain': [('task_id', '=', self.id), ('requisition_type', '=', 'scrap')],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def material_reqsn_internal_action(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pways_construction_management.action_material_int_pick_requisition")
        action['domain'] = [('task_id', '=', self.id), ('requisition_type', '=', 'internal')]
        action['context'] = {
            'default_project_id': self.project_id.id,
            'default_task_id': self.id,
            'default_task_user_ids': self.user_ids.ids,
            'default_job_cost_id': self.job_cost_id.id,
            'default_analytic_account_id': self.analytic_account_id.id,
            'default_requisition_type': 'internal',
        }        
        return action

    def all_bills_action(self):
        all_bills = self.env['account.move'].search([('task_id', '=', self.id)])
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills',
            'res_model': 'account.move',
            'domain': [('id', 'in', all_bills.ids)],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def open_picking_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Consume Material',
            'res_model': 'stock.picking',
            'domain': [('task_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
        }
        
    # def view_stock_moves(self):
    #     for rec in self:
    #         stock_move_list = []
    #         for move in rec.move_ids:
    #             stock_move_list += move.requisition_id.delivery_picking_id.move_line_ids.ids
    #     result = self.env["ir.actions.actions"]._for_xml_id("stock.stock_move_action")
    #     result['domain'] = str([('id', 'in', stock_move_list)])
    #     return result

    def view_stock_moves(self):
        for rec in self:
            rec.total_stock_moves_count()
            stock_move_list = []
            for move in rec.stock_picking_ids:
                stock_move_list += move.move_line_ids.ids
        result = self.env["ir.actions.actions"]._for_xml_id("stock.stock_move_action")
        result['domain'] = str([('id', 'in', stock_move_list)])
        return result    

    def stock_view_action(self):
        material_plan_ids = self.material_plan_ids.mapped('product_id')
        self.ensure_one()
        stock_action = self.env['ir.actions.act_window']._for_xml_id('stock.action_product_stock_view')
        stock_action['domain'] = str([('id', 'in', material_plan_ids.ids)])
        return stock_action

    ###### Super methods ######

    @api.model
    def create(self,vals):
        number = self.env['ir.sequence'].next_by_code('project.task')
        vals.update({
            'job_number': number,
        })
        return super(ProjectTask, self).create(vals) 

    ###### Normal button methods ######

    def action_subtask(self):
        res = super(ProjectTask, self).action_subtask()
        res['context'].update({
            'default_parent_task_id': self.id,
        })
        return res

    def btn_out_pick_consume_prod(self):
        vals = {
                'name': 'Picking Wizard',
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'task.picking.wizard',
                'target': 'new',
            }
        return vals
