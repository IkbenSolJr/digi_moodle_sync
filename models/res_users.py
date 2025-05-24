# -*- coding: utf-8 -*-
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    moodle_id = fields.Integer(string='Moodle ID', readonly=True) 