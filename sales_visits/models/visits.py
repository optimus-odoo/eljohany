import math

from odoo import models, fields, api,_

class CustomField(models.Model):
    _name = "visit.type"
    _description = "Visit Type"

    name = fields.Char("Option Name")
    points = fields.Integer()

class Visit(models.Model):
    _name = 'visit.visit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Visit'

    name = fields.Char(default=_('New'), copy=False)
    description = fields.Text()
    start_date = fields.Datetime()
    end_date = fields.Datetime()
    partner_id = fields.Many2one('res.partner','Client')
    salesperson_id = fields.Many2one('res.users','Salesperson')
    visit_type_id = fields.Many2many('visit.type', string="Visit Type")
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Open'), ('close', 'Closed')],
        default='open',
        tracking=True,
    )
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.user.company_id)
    in_url = fields.Char()
    out_url = fields.Char()
    message_in = fields.Char()
    message_out = fields.Char()
    in_latitude = fields.Char("Latitude ")
    in_longitude = fields.Char("Longitude ")
    out_latitude = fields.Char("Latitude")
    out_longitude = fields.Char("Longitude")
    in_compliant = fields.Selection([('yes', 'Compliant'), ('no', 'Not Compliant')], default='yes',
                                    string="Checkin Compliant")
    out_compliant = fields.Selection([('yes', 'Compliant'), ('no', 'Not Compliant')], default='yes',
                                     string="Checkout Compliant")
    duration = fields.Float(compute='_compute_duration', string="Duration", store=True)
    points = fields.Integer(compute='_compute_points', string="Points", store=True)
    collected = fields.Boolean(default=False, string="Points Collected")
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('client.visit') or _('New')
            if all(key in vals for key in ('in_latitude', 'in_longitude', 'partner_id')):
                vals['in_compliant'] = 'yes'
                if not self.is_in_range(
                    vals['in_latitude'], vals['in_longitude'], vals['partner_id']
                ):
                    vals['in_compliant'] = 'no'
        return super().create(vals_list)

    def write(self, vals):
        if vals and 'out_latitude' in vals and 'out_longitude' in vals:
            vals['out_compliant'] = 'yes'
            if not self.is_in_range(vals['out_latitude'], vals['out_longitude'], self.partner_id.id):
                vals['out_compliant'] = 'no'
        return super().write(vals)

    def is_in_range(self, latitude, longitude, partner_id):
        """
        This function checks if the given latitude and longitude are within 2 miles
        of the partner's stored latitude and longitude.

        Args:
            latitude (float): Latitude of the point to check.
            longitude (float): Longitude of the point to check.
            partner_id (int): ID of the partner (res.partner) to compare against.

        Returns:
            bool: True if the point is within 2 miles of the partner's location, False otherwise.
        """

        partner = self.env['res.partner'].browse(partner_id)
        allowed_distance = float(self.env['ir.config_parameter'].sudo().get_param('sales_visits.max_distance', 0.0))
        # Ensure partner has latitude and longitude data
        if not partner.partner_latitude or not partner.partner_longitude:
            return False

        # Haversine formula constants
        R = 3958.8  # Radius of the Earth in miles

        # Convert degrees to radians
        lat1 = math.radians(partner.partner_latitude)
        lon1 = math.radians(partner.partner_longitude)
        lat2 = math.radians(latitude)
        lon2 = math.radians(longitude)

        # Difference in coordinates
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        # Haversine formula
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        # Distance in miles
        distance = R * c

        # Check if the distance is within 2 miles
        return distance <= allowed_distance
    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                rec.duration = (rec.end_date - rec.start_date).total_seconds() / 3600
            else:
                rec.duration = 0

    @api.depends('visit_type_id')
    def _compute_points(self):
        for rec in self:
            points = 0
            for visit in rec.visit_type_id:
                points += visit.points
            rec.points = points
