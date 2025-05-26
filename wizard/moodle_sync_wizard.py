# -*- coding: utf-8 -*-
import logging
import requests
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError
from datetime import datetime
# Import the controller
from odoo.addons.digi_moodle_sync.controllers.teacher_sync import MoodleTeacherSync # Adjusted import path

_logger = logging.getLogger(__name__)

MOODLE_SYNC_MANAGER_GROUP = 'digi_moodle_sync.group_manager' # Define group name

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

    def _check_access_rights_for_wizard(self):
        # Tạm thời bỏ kiểm tra quyền để cho phép tất cả người dùng thực hiện đồng bộ
        return True
        # if not self.env.user.has_group(MOODLE_SYNC_MANAGER_GROUP):
        #     _logger.warning(
        #         f"User {self.env.user.login} (ID: {self.env.user.id}) attempt to run Moodle Sync Wizard without proper rights."
        #     )
        #     raise AccessError(_("Bạn không có quyền thực hiện hành động này. Vui lòng liên hệ quản trị viên."))

    def action_sync(self):
        # Access Check for Wizard execution
        try:
            self._check_access_rights_for_wizard()
        except AccessError as e:
            # Return a notification for UI
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Access Denied'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        _logger.info(f"Moodle Sync Wizard initiated by User {self.env.user.login} (ID: {self.env.user.id}) with sync_type: {self.sync_type}")

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
            _logger.info("Wizard: Starting teacher synchronization...")
            try:
                # Instantiate the controller
                # Ensure MoodleTeacherSync is imported at the top of the file:
                # from odoo.addons.digi_moodle_sync.controllers.teacher_sync import MoodleTeacherSync
                teacher_sync_controller = MoodleTeacherSync()
                
                # Calling controller methods directly like this is generally not recommended
                # as they are designed for HTTP requests and might depend on `odoo.http.request`.
                # A better long-term solution is to move the core sync logic to a model method
                # that both the controller and wizard can call.
                # For this refactoring, we proceed with the direct call, assuming `request.env`
                # is available or the controller method is simple enough.
                
                # Simulate a basic request object if the controller heavily relies on it.
                # For now, we pass 'self.env' which is available in wizard methods.
                # The controller's sync_teachers might need to be adapted to accept `env`
                # or to work without a full HTTP request context if it uses `request.env`
                
                # Attempt to call with current environment if controller logic can handle it
                # This is a simplification. Proper context passing or a shared model method is ideal.
                with self.env.cr.savepoint(): # Use a savepoint for safety
                    # The controller's sync_teachers doesn't take specific arguments other than **kwargs
                    # which are http params. It internally gets config and courses.
                    result_message = teacher_sync_controller.sync_teachers() 
                
                _logger.info(f"Wizard: Teacher synchronization via controller result: {result_message}")

            except Exception as e:
                _logger.error(f"Wizard: Error during teacher synchronization via controller: {str(e)}", exc_info=True)
                # Show an error to the user
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Teacher Sync Error'),
                        'message': _('Failed to sync teachers: %s') % str(e),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
            _logger.info("Wizard: Teacher synchronization finished.")

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
                            _logger.debug(f"Đã tạo người dùng mới: {email}")

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
                                'timemodified': activity.get('timemodified'),
                                'last_sync_date': datetime.now(),
                            }

                            progress = self.env['moodle.activity.progress'].search([
                                ('userid', '=', user.id),
                                ('courseid', '=', course.id),
                                ('cmid', '=', activity['cmid'])
                            ])

                            if progress:
                                progress.write(vals)
                                _logger.debug(f"Updated progress for user {user.name} in course {course.name}, activity {activity.get('activityname', '')}")
                            else:
                                self.env['moodle.activity.progress'].create(vals)
                                _logger.debug(f"Created progress for user {user.name} in course {course.name}, activity {activity.get('activityname', '')}")

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
                                'course_id': course.id,
                                'last_sync_date': datetime.now(),
                            }

                            assign = self.env['moodle.assignment'].search([
                                ('moodle_id', '=', assignment['id'])
                            ])

                            if assign:
                                assign.write(vals)
                                _logger.debug(f"Updated assignment {assignment['name']} for course {course.name}")
                            else:
                                self.env['moodle.assignment'].create(vals)
                                _logger.debug(f"Created assignment {assignment['name']} for course {course.name}")

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
                                'grade': submission.get('grade'),
                                'last_sync_date': datetime.now(),
                            }

                            sub = self.env['moodle.assignment.submission'].search([
                                ('assignment_id', '=', assignment.id),
                                ('user_id', '=', user.id)
                            ])

                            if sub:
                                sub.write(vals)
                                _logger.debug(f"Updated submission for user {user.name} in assignment {assignment.name}")
                            else:
                                self.env['moodle.assignment.submission'].create(vals)
                                _logger.debug(f"Created submission for user {user.name} in assignment {assignment.name}")

            except Exception as e:
                _logger.error(f"Error syncing submissions for assignment {assignment.name}: {str(e)}")

    # The old _sync_teachers method in the wizard should be REMOVED by this edit.
    # If it's not, it means the `// ... existing code ...` marker was not placed correctly
    # to signal the complete replacement of the _sync_teachers method block.
    # Ensure the entire old _sync_teachers method is replaced.
    
    # [This is where the old _sync_teachers method was, it should be deleted by the edit]
    # For example, if the old method was:
    # def _sync_teachers(self, config):
    #    # ... old logic here ...
    #    pass
    # The edit should replace this entire block.
    # ... existing code ... 