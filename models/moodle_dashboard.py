# -*- coding: utf-8 -*-
import json
from odoo import models, fields, api, _
from datetime import datetime

class MoodleDashboard(models.TransientModel):
    _name = 'moodle.dashboard'
    _description = 'Moodle Sync Dashboard'
    
    last_sync_date     = fields.Datetime('Thời gian đồng bộ cuối', readonly=True)
    courses_count      = fields.Integer('Số khóa học', compute='_compute_counts')
    users_count        = fields.Integer('Số học viên', compute='_compute_counts')
    enrollments_count  = fields.Integer('Số đăng ký', compute='_compute_counts')
    grades_count       = fields.Integer('Số điểm', compute='_compute_counts')
    moodle_url         = fields.Char('URL Moodle', compute='_compute_conn')
    connection_state   = fields.Selection([
        ('connected','Đã kết nối'),('disconnected','Chưa kết nối')],
        compute='_compute_conn', string='Trạng thái'
    )
    enrollments_chart  = fields.Text('Biểu đồ đăng ký', compute='_compute_charts')
    grades_chart       = fields.Text('Biểu đồ điểm', compute='_compute_charts')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        last = self.env['ir.config_parameter'].sudo().get_param(
            'digi_moodle_sync.last_sync_date')
        if last:
            res['last_sync_date'] = last
        return res

    def _compute_counts(self):
        self.courses_count     = self.env['moodle.course'].search_count([])
        self.users_count       = self.env['moodle.user'].search_count([])
        self.enrollments_count = self.env['moodle.user.course'].search_count([])
        self.grades_count      = self.env['moodle.user.grade'].search_count([])

    def _compute_conn(self):
        url   = self.env['ir.config_parameter'].sudo().get_param(
            'digi_moodle_sync.moodle_url') or ''
        token = self.env['ir.config_parameter'].sudo().get_param(
            'digi_moodle_sync.token')
        self.moodle_url       = url or _('Chưa cấu hình')
        self.connection_state = 'connected' if token else 'disconnected'

    def _compute_charts(self):
        # Tương tự như cũ, chỉ đảm bảo không dùng tham số cũ
        # ... (giữ nguyên logic JSON của bạn) ...
        pass

    # hành động mở form/list
    def action_view_courses(self): ...
    def action_view_users(self): ...
    def action_view_enrollments(self): ...
    def action_view_grades(self): ...
    def action_test_connection(self): ...
