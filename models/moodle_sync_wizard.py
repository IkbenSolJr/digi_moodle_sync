# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MoodleSyncWizard(models.TransientModel):
    _name = 'moodle.sync.wizard'
    _description = 'Wizard đồng bộ từ Moodle'

    sync_courses       = fields.Boolean('Khóa học', default=True)
    sync_users         = fields.Boolean('Người dùng', default=True)
    sync_user_courses  = fields.Boolean('Khóa học của người dùng', default=True)
    sync_grades        = fields.Boolean('Điểm số', default=True)

    def action_sync(self):
        self.ensure_one()
        config     = self.env['ir.config_parameter'].sudo()
        moodle_url = config.get_param('digi_moodle_sync.moodle_url') or ''
        token      = config.get_param('digi_moodle_sync.token') or ''
        if not moodle_url or not token:
            raise UserError(_('Vui lòng cấu hình URL và Token Moodle'))

        msg = ""
        if self.sync_courses:
            n = self.sync_courses_data(moodle_url, token)
            msg += _('Đã đồng bộ %s khóa học\n') % n
        if self.sync_users:
            m = self.sync_users_data(moodle_url, token)
            msg += _('Đã đồng bộ %s người dùng\n') % m
        if self.sync_user_courses:
            p = self.sync_user_courses_data(moodle_url, token)
            msg += _('Đã đồng bộ %s user-course\n') % p
        if self.sync_grades:
            q = self.sync_grades_data(moodle_url, token)
            msg += _('Đã đồng bộ %s điểm số\n') % q

        return {
            'type':'ir.actions.client','tag':'display_notification',
            'params':{'title':_('Hoàn tất'),'message':msg,'type':'success'}
        }

    def sync_courses_data(self, url, token, timeout=30):
        """Đồng bộ danh sách khóa học từ Moodle"""
        try:
            # Gọi API Moodle để lấy danh sách khóa học
            params = {'wstoken': token, 'wsfunction': 'core_course_get_courses',
                     'moodlewsrestformat': 'json'}
            response = requests.get(f"{url}/webservice/rest/server.php",
                                  params=params, timeout=timeout)
            courses = response.json()
            
            # Tạo/cập nhật khóa học trong Odoo
            Course = self.env['moodle.course'].sudo()
            count = 0
            for course in courses:
                vals = {
                    'name': course.get('fullname'),
                    'shortname': course.get('shortname'),
                    'moodle_id': course.get('id'),
                    'last_sync_date': fields.Datetime.now(),
                }
                course_rec = Course.search([('moodle_id','=',course.get('id'))], limit=1)
                if course_rec:
                    course_rec.write(vals)
                else:
                    Course.create(vals)
                count += 1
            return count
        except Exception as e:
            raise UserError(_('Lỗi khi đồng bộ khóa học: %s') % str(e))

    def sync_users_data(self, url, token, timeout=30):
        """Đồng bộ danh sách người dùng từ Moodle"""
        try:
            # Gọi API Moodle để lấy danh sách người dùng
            params = {'wstoken': token, 'wsfunction': 'core_user_get_users',
                     'moodlewsrestformat': 'json', 'criteria[0][key]': 'email',
                     'criteria[0][value]': '%'}  # Lấy tất cả users
            response = requests.get(f"{url}/webservice/rest/server.php",
                                  params=params, timeout=timeout)
            users = response.json().get('users', [])
            
            # Tạo/cập nhật người dùng trong Odoo
            User = self.env['moodle.user'].sudo()
            count = 0
            for user in users:
                vals = {
                    'name': user.get('fullname'),
                    'login': user.get('username'),
                    'email': user.get('email'),
                    'moodle_id': user.get('id'),
                    'last_sync_date': fields.Datetime.now(),
                }
                user_rec = User.search([('moodle_id','=',user.get('id'))], limit=1)
                if user_rec:
                    user_rec.write(vals)
                else:
                    User.create(vals)
                count += 1
            return count
        except Exception as e:
            raise UserError(_('Lỗi khi đồng bộ người dùng: %s') % str(e))

    def sync_user_courses_data(self, url, token, timeout=30):
        """Đồng bộ danh sách khóa học của người dùng từ Moodle"""
        try:
            # Lấy danh sách người dùng Moodle trong Odoo
            users = self.env['moodle.user'].sudo().search([])
            if not users:
                return 0

            UserCourse = self.env['moodle.user.course'].sudo()
            count = 0
            
            for user in users:
                # Gọi API Moodle để lấy khóa học của từng user
                params = {'wstoken': token, 
                         'wsfunction': 'core_enrol_get_users_courses',
                         'moodlewsrestformat': 'json',
                         'userid': user.moodle_id}
                response = requests.get(f"{url}/webservice/rest/server.php",
                                      params=params, timeout=timeout)
                courses = response.json()
                
                for course in courses:
                    vals = {
                        'user_id': user.id,
                        'moodle_course_id': course.get('id'),
                        'course_name': course.get('fullname'),
                        'course_shortname': course.get('shortname'),
                        'enrol_date': fields.Datetime.now(),  # Moodle API không trả về ngày ghi danh
                        'completion_state': 'in_progress',
                        'progress_percent': course.get('progress', 0.0),
                        'last_sync_date': fields.Datetime.now(),
                    }
                    user_course = UserCourse.search([
                        ('user_id','=',user.id),
                        ('moodle_course_id','=',course.get('id'))
                    ], limit=1)
                    if user_course:
                        user_course.write(vals)
                    else:
                        UserCourse.create(vals)
                    count += 1
            return count
        except Exception as e:
            raise UserError(_('Lỗi khi đồng bộ khóa học của người dùng: %s') % str(e))

    def sync_grades_data(self, url, token, timeout=30):
        """Đồng bộ điểm số từ Moodle"""
        try:
            # Lấy danh sách user courses
            user_courses = self.env['moodle.user.course'].sudo().search([])
            if not user_courses:
                return 0

            Grade = self.env['moodle.user.grade'].sudo()
            count = 0
            
            for uc in user_courses:
                # Gọi API Moodle để lấy điểm số
                params = {'wstoken': token,
                         'wsfunction': 'gradereport_user_get_grade_items',
                         'moodlewsrestformat': 'json',
                         'courseid': uc.moodle_course_id,
                         'userid': uc.user_id.moodle_id}
                response = requests.get(f"{url}/webservice/rest/server.php",
                                      params=params, timeout=timeout)
                data = response.json()
                grade_items = data.get('gradeitems', [])
                
                for item in grade_items:
                    vals = {
                        'moodle_user_id': uc.user_id.id,
                        'moodle_course_id': uc.id,
                        'moodle_item_id': item.get('id'),
                        'item_name': item.get('itemname'),
                        'item_type': item.get('itemtype'),
                        'item_module': item.get('itemmodule'),
                        'grade': float(item.get('graderaw', 0.0)),
                        'grade_date': item.get('gradedatesubmitted'),
                        'last_sync_date': fields.Datetime.now(),
                    }
                    grade = Grade.search([
                        ('moodle_user_id','=',uc.user_id.id),
                        ('moodle_course_id','=',uc.id),
                        ('moodle_item_id','=',item.get('id'))
                    ], limit=1)
                    if grade:
                        grade.write(vals)
                    else:
                        Grade.create(vals)
                    count += 1
            return count
        except Exception as e:
            raise UserError(_('Lỗi khi đồng bộ điểm số: %s') % str(e))
