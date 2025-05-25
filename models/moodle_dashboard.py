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
        # Tạo dữ liệu biểu đồ đơn giản
        self.enrollments_chart = json.dumps({
            'data': [
                {'label': 'Đang học', 'value': self.env['moodle.user.course'].search_count([('completion_state', '=', 'in_progress')])},
                {'label': 'Hoàn thành', 'value': self.env['moodle.user.course'].search_count([('completion_state', '=', 'completed')])},
                {'label': 'Chưa bắt đầu', 'value': self.env['moodle.user.course'].search_count([('completion_state', '=', 'not_started')])}
            ]
        })
        
        # Dữ liệu điểm số
        self.grades_chart = json.dumps({
            'data': [
                {'label': 'Đạt', 'value': self.env['moodle.user.grade'].search_count([('grade', '>=', 5)])},
                {'label': 'Chưa đạt', 'value': self.env['moodle.user.grade'].search_count([('grade', '<', 5)])}
            ]
        })

    # hành động mở form/list
    def action_view_courses(self): 
        return self.env["ir.actions.actions"]._for_xml_id("digi_moodle_sync.action_moodle_course")
    
    def action_view_users(self): 
        return self.env["ir.actions.actions"]._for_xml_id("digi_moodle_sync.action_moodle_user")
    
    def action_view_enrollments(self): 
        return self.env["ir.actions.actions"]._for_xml_id("digi_moodle_sync.action_moodle_user_course")
    
    def action_view_grades(self): 
        return self.env["ir.actions.actions"]._for_xml_id("digi_moodle_sync.action_moodle_user_grade")
    
    def action_test_connection(self):
        import requests
        
        config = self.env['ir.config_parameter'].sudo()
        moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token = config.get_param('digi_moodle_sync.token')
        
        if not moodle_url or not token:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Lỗi cấu hình'),
                    'message': _('Vui lòng cấu hình URL Moodle và token trước'),
                    'sticky': False,
                    'type': 'danger'
                }
            }
        
        # Thêm /webservice/rest/server.php vào URL
        api_url = moodle_url
        if not api_url.endswith('/'):
            api_url += '/'
        api_url += 'webservice/rest/server.php'
        
        params = {
            'wstoken': token,
            'wsfunction': 'core_webservice_get_site_info',
            'moodlewsrestformat': 'json'
        }
        
        try:
            resp = requests.get(api_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if 'sitename' in data:
                config.set_param('digi_moodle_sync.last_sync_date', fields.Datetime.now())
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Kết nối thành công'),
                        'message': _('Đã kết nối với: %s') % data.get('sitename', ''),
                        'sticky': False,
                        'type': 'success'
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi'),
                        'message': _('Phản hồi không hợp lệ từ Moodle'),
                        'sticky': False,
                        'type': 'danger'
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Lỗi kết nối'),
                    'message': str(e),
                    'sticky': False,
                    'type': 'danger'
                }
            }
