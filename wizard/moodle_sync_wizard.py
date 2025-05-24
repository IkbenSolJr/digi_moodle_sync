# -*- coding: utf-8 -*-
import logging
import requests
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime

_logger = logging.getLogger(__name__)

class MoodleSyncWizard(models.TransientModel):
    _name = 'moodle.sync.wizard'
    _description = 'Moodle Sync Wizard'

    sync_type = fields.Selection([
        ('activity', 'Activity Progress'),
        ('assignment', 'Assignments'),
        ('submission', 'Assignment Submissions'),
        ('teacher', 'Course Teachers'),
        ('all', 'All Data')
    ], string='Sync Type', default='all', required=True)

    def _get_moodle_config(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'token': params.get_param('digi_moodle_sync.token'),
            'url': params.get_param('digi_moodle_sync.moodle_url')
        }

    def action_sync(self):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Moodle configuration is missing. Please configure token and URL.',
                    'type': 'danger',
                    'sticky': False,
                }
            }

        # Sync users first
        self._sync_users(config)

        if self.sync_type in ['activity', 'all']:
            self._sync_activities(config)
        if self.sync_type in ['assignment', 'all']:
            self._sync_assignments(config)
        if self.sync_type in ['submission', 'all']:
            self._sync_submissions(config)
        if self.sync_type in ['teacher', 'all']:
            self._sync_teachers(config)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Data synchronized successfully',
                'type': 'success',
                'sticky': False,
            }
        }

    def _sync_users(self, config):
        """Đồng bộ người dùng từ Moodle sang Odoo"""
        params = {
            'wstoken': config['token'],
            'wsfunction': 'core_user_get_users',
            'criteria[0][key]': 'email',
            'criteria[0][value]': '%',  # Lấy tất cả người dùng
            'moodlewsrestformat': 'json'
        }

        try:
            response = requests.get(f"{config['url']}/webservice/rest/server.php", params=params)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and 'users' in data:
                for user_data in data['users']:
                    email = user_data.get('email')
                    if not email:
                        continue

                    # Tìm user trong Odoo bằng email
                    user = self.env['res.users'].search([('login', '=', email)], limit=1)
                    
                    if user:
                        # Cập nhật moodle_id cho user hiện có
                        user.write({
                            'moodle_id': user_data.get('id'),
                            'name': f"{user_data.get('firstname', '')} {user_data.get('lastname', '')}".strip()
                        })
                    else:
                        # Tạo partner và user mới
                        try:
                            # Tạo partner trước
                            partner_vals = {
                                'name': f"{user_data.get('firstname', '')} {user_data.get('lastname', '')}".strip(),
                                'email': email,
                                'company_id': self.env.company.id,
                            }
                            partner = self.env['res.partner'].create(partner_vals)

                            # Tạo user mới
                            user_vals = {
                                'login': email,
                                'partner_id': partner.id,
                                'company_id': self.env.company.id,
                                'company_ids': [(4, self.env.company.id)],
                                'moodle_id': user_data.get('id'),
                                'groups_id': [(4, self.env.ref('base.group_user').id)],  # Thêm vào nhóm Internal User
                            }
                            new_user = self.env['res.users'].with_context(no_reset_password=True).create(user_vals)
                            _logger.info(f"Đã tạo người dùng mới: {email}")

                        except Exception as e:
                            _logger.error(f"Lỗi khi tạo người dùng {email}: {str(e)}")

        except Exception as e:
            _logger.error(f"Lỗi khi đồng bộ người dùng từ Moodle: {str(e)}")

    def _sync_activities(self, config):
        courses = self.env['moodle.course'].search([])
        users = self.env['res.users'].search([('moodle_id', '!=', False)])

        for course in courses:
            for user in users:
                params = {
                    'wstoken': config['token'],
                    'wsfunction': 'core_completion_get_activities_completion_status',
                    'courseid': course.moodle_id,
                    'userid': user.moodle_id,
                    'moodlewsrestformat': 'json'
                }

                try:
                    response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
                    response.raise_for_status()
                    data = response.json()

                    if 'statuses' in data:
                        for activity in data['statuses']:
                            vals = {
                                'userid': user.id,
                                'courseid': course.id,
                                'cmid': activity['cmid'],
                                'activity_name': activity.get('activityname', ''),
                                'completionstate': str(activity['completionstate']),
                                'timemodified': activity.get('timemodified')
                            }

                            progress = self.env['moodle.activity.progress'].search([
                                ('userid', '=', user.id),
                                ('courseid', '=', course.id),
                                ('cmid', '=', activity['cmid'])
                            ])

                            if progress:
                                progress.write(vals)
                            else:
                                self.env['moodle.activity.progress'].create(vals)

                except Exception as e:
                    _logger.error(f"Error syncing progress for user {user.name} in course {course.name}: {str(e)}")

    def _sync_assignments(self, config):
        courses = self.env['moodle.course'].search([])
        
        for course in courses:
            params = {
                'wstoken': config['token'],
                'wsfunction': 'mod_assign_get_assignments',
                'courseids[]': course.moodle_id,
                'moodlewsrestformat': 'json'
            }

            try:
                response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
                response.raise_for_status()
                data = response.json()

                if 'courses' in data:
                    for course_data in data['courses']:
                        for assignment in course_data.get('assignments', []):
                            vals = {
                                'moodle_id': assignment['id'],
                                'name': assignment['name'],
                                'duedate': assignment.get('duedate'),
                                'course_id': course.id
                            }

                            assign = self.env['moodle.assignment'].search([
                                ('moodle_id', '=', assignment['id'])
                            ])

                            if assign:
                                assign.write(vals)
                            else:
                                self.env['moodle.assignment'].create(vals)

            except Exception as e:
                _logger.error(f"Error syncing assignments for course {course.name}: {str(e)}")

    def _sync_submissions(self, config):
        assignments = self.env['moodle.assignment'].search([])
        
        for assignment in assignments:
            params = {
                'wstoken': config['token'],
                'wsfunction': 'mod_assign_get_submissions',
                'assignmentids[]': assignment.moodle_id,
                'moodlewsrestformat': 'json'
            }

            try:
                response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
                response.raise_for_status()
                data = response.json()

                if 'assignments' in data:
                    for assign_data in data['assignments']:
                        for submission in assign_data.get('submissions', []):
                            user = self.env['res.users'].search([
                                ('moodle_id', '=', submission['userid'])
                            ])
                            if not user:
                                continue

                            vals = {
                                'assignment_id': assignment.id,
                                'user_id': user.id,
                                'status': submission['status'],
                                'timemodified': submission.get('timemodified'),
                                'grade': submission.get('grade')
                            }

                            sub = self.env['moodle.assignment.submission'].search([
                                ('assignment_id', '=', assignment.id),
                                ('user_id', '=', user.id)
                            ])

                            if sub:
                                sub.write(vals)
                            else:
                                self.env['moodle.assignment.submission'].create(vals)

            except Exception as e:
                _logger.error(f"Error syncing submissions for assignment {assignment.name}: {str(e)}")

    def _sync_teachers(self, config):
        courses = self.env['moodle.course'].search([])
        
        for course in courses:
            params = {
                'wstoken': config['token'],
                'wsfunction': 'core_enrol_get_enrolled_users',
                'courseid': course.moodle_id,
                'moodlewsrestformat': 'json'
            }

            try:
                response = requests.get(f"{config['url']}/webservice/rest/server.php", params=params)
                response.raise_for_status()
                data = response.json()

                _logger.info(f"Syncing teachers for course {course.name}")
                _logger.info(f"Found {len(data)} enrolled users")

                if isinstance(data, list):
                    for user_data in data:
                        roles = user_data.get('roles', [])
                        if isinstance(roles, list) and any(role.get('roleid') == 3 for role in roles):  # 3 is teacher role
                            user = self.env['res.users'].search([('moodle_id', '=', user_data.get('id'))], limit=1)
                            if not user:
                                continue

                            vals = {
                                'course_id': course.id,
                                'user_id': user.id,
                                'moodle_id': user_data.get('id')
                            }

                            teacher = self.env['moodle.course.teacher'].search([
                                ('course_id', '=', course.id),
                                ('user_id', '=', user.id)
                            ])

                            if teacher:
                                teacher.write(vals)
                            else:
                                self.env['moodle.course.teacher'].create(vals)

            except Exception as e:
                _logger.error(f"Error syncing teachers for course {course.name}: {str(e)}") 