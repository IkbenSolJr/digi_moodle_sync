# -*- coding: utf-8 -*-
import logging
import requests
import json
from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class MoodleCourseGradeSyncController(http.Controller):

    @http.route('/moodle/sync_all_courses_grades', type='http', auth='public', methods=['GET'], csrf=False)
    def sync_all(self, **kw):
        config     = request.env['ir.config_parameter'].sudo()
        moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token      = config.get_param('digi_moodle_sync.token')

        # Thêm /webservice/rest/server.php vào URL
        api_url = moodle_url
        if not api_url.endswith('/'):
            api_url += '/'
        api_url += 'webservice/rest/server.php'

        users   = request.env['res.users'].sudo().search([('moodle_id', '>', 0)])
        _logger.info("Syncing courses and grades for %d Moodle users", len(users))
        
        results = {}
        for u in users:
            try:
                results[u.id] = self._sync_user(u.id, u.moodle_id, api_url, token)
            except Exception as e:
                _logger.error("Error syncing user %s (moodle_id: %s): %s", u.id, u.moodle_id, e)
                results[u.id] = {'error': str(e)}

        return request.make_response(
            json.dumps({'message':'Full sync completed','results':results}),
            headers=[('Content-Type','application/json')])

    @http.route('/moodle/sync_courses_grades', type='http', auth='public', methods=['GET'], csrf=False)
    def sync_one(self, **kw):
        config     = request.env['ir.config_parameter'].sudo()
        moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token      = config.get_param('digi_moodle_sync.token')

        # Thêm /webservice/rest/server.php vào URL
        api_url = moodle_url
        if not api_url.endswith('/'):
            api_url += '/'
        api_url += 'webservice/rest/server.php'

        uid = kw.get('userid')
        if not uid:
            return request.make_response(
                json.dumps({'error':'Missing parameter userid'}),
                headers=[('Content-Type','application/json')])
        try:
            user = request.env['res.users'].sudo().browse(int(uid))
            if not user or not user.moodle_id:
                return request.make_response(
                    json.dumps({'error':'User không có Moodle ID'}),
                    headers=[('Content-Type','application/json')])
                
            data = self._sync_user(user.id, user.moodle_id, api_url, token)
            return request.make_response(
                json.dumps({'message':'Sync completed','result':data}),
                headers=[('Content-Type','application/json')])
        except Exception as e:
            _logger.error("Error syncing user %s: %s", uid, e)
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[('Content-Type','application/json')])

    def _sync_user(self, odoo_user_id, moodle_user_id, url, token):
        # 1) Lấy course list
        params = {
            'wstoken':            token,
            'wsfunction':         'core_enrol_get_users_courses',
            'moodlewsrestformat': 'json',
            'userid':             moodle_user_id  # Dùng Moodle ID, không phải Odoo ID
        }
        
        _logger.info("Calling Moodle API to get courses for user %s (moodle_id: %s)", odoo_user_id, moodle_user_id)
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            _logger.error("API error: status %s, response: %s", r.status_code, r.text[:200])
            raise Exception(f"API error: {r.status_code}")
            
        r.raise_for_status()
        courses = r.json() or []
        _logger.info("Retrieved %d courses for user", len(courses))

        UserCourse = request.env['moodle.user.course'].sudo()
        Grade      = request.env['moodle.user.grade'].sudo()
        MoodleUser = request.env['moodle.user'].sudo()
        
        # Đảm bảo có bản ghi moodle.user
        moodle_user = MoodleUser.search([('moodle_id', '=', moodle_user_id)], limit=1)
        if not moodle_user:
            user = request.env['res.users'].sudo().browse(odoo_user_id)
            moodle_user = MoodleUser.create({
                'name': user.name,
                'login': user.login,
                'email': user.email or '',
                'moodle_id': moodle_user_id,
                'odoo_user_id': odoo_user_id,
                'last_sync_date': datetime.now(),
            })
        
        out = {}

        for c in courses:
            cid      = c.get('id')
            cname    = c.get('fullname') or 'Unknown'
            # Tạo hoặc cập nhật record khóa học
            uc = UserCourse.search([
                ('moodle_course_id', '=', cid),
                ('moodle_user_id', '=', moodle_user.id)  # Quan hệ với moodle.user
            ], limit=1)
            
            if not uc:
                uc = UserCourse.create({
                    'moodle_course_id': cid,
                    'moodle_user_id': moodle_user.id,  # Quan hệ với moodle.user
                    'course_name': cname,
                    'course_shortname': c.get('shortname') or ''
                })

            # 2) Lấy grades
            gp = {
                'wstoken':            token,
                'wsfunction':         'gradereport_user_get_grade_items',
                'moodlewsrestformat': 'json',
                'userid':             moodle_user_id,  # Dùng Moodle ID
                'courseid':           cid
            }
            
            _logger.info("Getting grades for course %s", cid)
            gr = requests.get(url, params=gp, timeout=15)
            if gr.status_code != 200:
                _logger.error("Grade API error: status %s, response: %s", gr.status_code, gr.text[:200])
                continue
                
            gr.raise_for_status()
            gd = gr.json() or {}

            grades = []
            for ug in gd.get('usergrades', []):
                for g in ug.get('gradeitems', []):
                    item = self._process_grade(g, moodle_user.id, uc.id, Grade)
                    if item:
                        grades.append(item)
            out[cid] = {'course': cname, 'grades': grades}

        return out

    def _process_grade(self, gitem, moodle_user_id, uc_id, GradeModel):
        try:
            mid     = gitem.get('id')
            if not mid:
                return
            val     = gitem.get('gradeformatted') or '-'
            ts      = gitem.get('gradedategraded') or 0
            gdate   = datetime.fromtimestamp(ts) if ts else False
            iname   = gitem.get('itemname') or 'Unnamed Item'
            # Tìm hoặc tạo grade record
            existing = GradeModel.search([
                ('moodle_user_id','=', moodle_user_id),  # Quan hệ với moodle.user
                ('moodle_course_id','=', uc_id),
                ('moodle_item_id','=', mid)
            ], limit=1)
            data = {
                'grade':       str(val),
                'graded_date': gdate,
                'item_name':   iname,
                'item_type':   gitem.get('itemtype'),
                'item_module': gitem.get('itemmodule'),
            }
            if existing:
                existing.write(data)
            else:
                GradeModel.create({
                    'moodle_user_id': moodle_user_id,  # Quan hệ với moodle.user
                    'moodle_course_id': uc_id,
                    'moodle_item_id':   mid,
                    **data
                })
            return data
        except Exception as e:
            _logger.error("Error processing grade item: %s", e)
            return
