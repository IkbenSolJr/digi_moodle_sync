# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class MoodleCourse(models.Model):
    _name = 'moodle.course'
    _description = 'Moodle Course'

    name = fields.Char('Tên khóa học', required=True)
    shortname = fields.Char('Mã khóa học', required=True)
    moodle_id = fields.Integer('ID Moodle', index=True)
    active = fields.Boolean('Kích hoạt', default=True)
    last_sync_date = fields.Datetime('Lần đồng bộ cuối', readonly=True)

    _sql_constraints = [
        ('unique_moodle_id',
         'unique(moodle_id)',
         'ID Moodle phải là duy nhất!')
    ]

    @api.model
    def action_create_sample_data_model(self):
        sample = [
            {'name':'Lập trình Python cơ bản','shortname':'PYTHON01','moodle_id':2001},
            {'name':'Phát triển ứng dụng Web','shortname':'WEB01','moodle_id':2002},
            {'name':'Quản trị hệ thống','shortname':'SYSADMIN','moodle_id':2003},
            {'name':'Tiếng Anh CNTT','shortname':'ENG-IT','moodle_id':2004},
        ]
        for data in sample:
            if not self.search([('shortname','=',data['shortname'])], limit=1):
                self.create(data)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Hoàn tất'),
                       'message': _('Đã tạo dữ liệu mẫu'),
                       'type': 'success'}
        }

    @api.model
    def test_moodle_connection(self):
        """Kiểm tra kết nối tới Moodle"""
        config = self.env['ir.config_parameter'].sudo()
        url   = config.get_param('digi_moodle_sync.moodle_url')
        token = config.get_param('digi_moodle_sync.token')
        if not url or not token:
            return {'status':'error','message':_('Thiếu URL hoặc Token')}
        try:
            res = requests.get(url, params={
                'wstoken':token,
                'wsfunction':'core_webservice_get_site_info',
                'moodlewsrestformat':'json'
            }, timeout=10)
            res.raise_for_status()
            info = res.json()
            return {'status':'success',
                    'message': _('Kết nối thành công tới %s') % info.get('sitename', '')}
        except Exception as e:
            _logger.error("test_connection failed: %s", e)
            return {'status':'error','message': _('Không thể kết nối: %s') % e}
