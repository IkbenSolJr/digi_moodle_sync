import requests
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class MoodleTeacherSync(http.Controller):
    
    def _get_moodle_config(self):
        params = request.env['ir.config_parameter'].sudo()
        return {
            'token': params.get_param('moodle.wstoken'),
            'url': params.get_param('moodle.url')
        }

    @http.route('/moodle/sync/teachers', type='http', auth='user')
    def sync_teachers(self, **kwargs):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get all courses
        courses = request.env['moodle.course'].search([])
        
        for course in courses:
            params = {
                'wstoken': config['token'],
                'wsfunction': 'core_enrol_get_enrolled_users',
                'courseid': course.moodle_id,
                'moodlewsrestformat': 'json'
            }

            try:
                response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
                response.raise_for_status()
                data = response.json()

                # Filter teachers from enrolled users
                teachers = [user for user in data if any(role['roleid'] == 3 for role in user.get('roles', []))]

                for teacher in teachers:
                    # Find or create user in Odoo
                    user = request.env['res.users'].search([
                        ('moodle_id', '=', teacher['id'])
                    ])
                    
                    if not user:
                        continue

                    vals = {
                        'user_id': user.id,
                        'course_id': course.id,
                        'fullname': teacher['fullname'],
                        'email': teacher.get('email', '')
                    }

                    # Create or update teacher record
                    teacher_record = request.env['moodle.course.teacher'].sudo().search([
                        ('user_id', '=', user.id),
                        ('course_id', '=', course.id)
                    ])

                    if teacher_record:
                        teacher_record.write(vals)
                    else:
                        request.env['moodle.course.teacher'].sudo().create(vals)

            except Exception as e:
                _logger.error(f"Error syncing teachers for course {course.name}: {str(e)}")
                continue

        return 'Teacher sync completed' 