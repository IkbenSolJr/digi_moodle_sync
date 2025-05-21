# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    moodle_url = fields.Char(
        string='URL Moodle API',
        config_parameter='digi_moodle_sync.moodle_url',
        help="Ví dụ: https://yourmoodle.com/webservice/rest/server.php"
    )
    moodle_token = fields.Char(
        string='Token Moodle',
        config_parameter='digi_moodle_sync.token'
    )
