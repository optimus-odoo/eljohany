from odoo import api, fields, models, _

class ConstructAttachmentsDocuments(models.Model):
    _name = 'construct.attachment.documents'
    _description = "Construct Attachment Documents"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default='New')
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    project_id = fields.Many2one('project.project')
    task_id = fields.Many2one('project.task')
    inspection_id = fields.Many2one('construct.inspector')
    compliance_id = fields.Many2one('construct.compliance')
    document_ids = fields.Many2many('ir.attachment', string="Documents")
    description = fields.Char()
