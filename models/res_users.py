# -*- coding: utf-8 -*-
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    moodle_id = fields.Integer(string='Moodle ID', readonly=True, copy=False)

    _sql_constraints = [
        ('unique_moodle_id_res_users', 'UNIQUE(moodle_id)', 'Moodle ID đã tồn tại trên một Odoo User khác!')
    ] 