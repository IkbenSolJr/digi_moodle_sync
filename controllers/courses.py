# -*- coding: utf-8 -*-
import logging
import requests
import json

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class MoodleCourseController(http.Controller):

    @http.route('/moodle/get_courses', type='http', auth='public', methods=['GET'], csrf=False)
    def get_moodle_courses(self, **kw):
        # Lấy cấu hình từ Settings
        config = request.env['ir.config_parameter'].sudo()
        moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token      = config.get_param('digi_moodle_sync.token')

        params = {
            'wstoken':            token,
            'wsfunction':         'core_course_get_courses',
            'moodlewsrestformat': 'json'
        }
        try:
            response = requests.get(moodle_url, params=params, timeout=15)
            response.raise_for_status()
            courses = response.json()

            MoodleCourse = request.env['moodle.course'].sudo()
            cr = request.env.cr
            for course in courses:
                cid = course.get('id')
                vals = {
                    'name':      course.get('fullname'),
                    'shortname': course.get('shortname'),
                }
                try:
                    existing = MoodleCourse.search([('moodle_id','=',cid)], limit=1)
                    if existing:
                        existing.write(vals)
                    else:
                        MoodleCourse.create({'moodle_id': cid, **vals})
                    cr.commit()
                except Exception as e:
                    _logger.error('Error syncing course %s: %s', cid, e)
                    cr.rollback()

            return request.make_response(
                json.dumps({'message': 'Courses synchronized successfully'}),
                headers=[('Content-Type','application/json')])
        except requests.RequestException as e:
            _logger.error('Moodle connection error: %s', e)
            return request.make_response(
                json.dumps({'error': f'Không thể kết nối Moodle: {e}'}),
                headers=[('Content-Type','application/json')])
        except Exception as e:
            _logger.error('Unexpected error: %s', e)
            return request.make_response(
                json.dumps({'error': f'Lỗi không xác định: {e}'}),
                headers=[('Content-Type','application/json')])
