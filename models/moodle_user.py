# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class MoodleUser(models.Model):
    _name = 'moodle.user'
    _description = 'Moodle User'
    _rec_name = 'name'

    name           = fields.Char("Full Name", required=True)
    login          = fields.Char("Login", required=True)
    email          = fields.Char("Email", required=True, index=True)
    moodle_id      = fields.Integer("Moodle ID", required=True, index=True)
    last_sync_date = fields.Datetime("Last Synced")
    odoo_user_id   = fields.Many2one(
        'res.users', string="Odoo User",
        help="Tài khoản Odoo liên kết"
    )

    _sql_constraints = [
        ('unique_email','unique(email)','Email đã tồn tại!'),
        ('unique_moodle_id','unique(moodle_id)','Moodle ID đã tồn tại!')
    ]

    def find_or_create_odoo_user(self):
        """Tìm hoặc tạo res.users dựa trên login/email"""
        self.ensure_one()
        User = self.env['res.users'].sudo()
        # tìm theo login
        user = User.search([('login','=', self.login)], limit=1)
        # nếu chưa có, tìm theo email
        if not user:
            user = User.search([('email','=', self.email)], limit=1)
        if user:
            self.odoo_user_id = user.id
            return user
        # chưa có => tạo mới
        vals = {
            'name':  self.name,
            'login': self.login,
            'email': self.email,
        }
        try:
            new_user = User.create(vals)
            self.odoo_user_id = new_user.id
            return new_user
        except Exception as e:
            raise UserError(_('Không thể tạo Odoo User: %s') % e)
