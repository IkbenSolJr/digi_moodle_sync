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
        
        # Define teacher role IDs (can be configured in Moodle settings)
        teacher_role_ids = [3, 4]  # 3: Teacher, 4: Non-editing teacher
        
        for course in courses:
            _logger.info(f"Syncing teachers for course: {course.name} (ID: {course.moodle_id})")
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

                # Log raw response for debugging
                _logger.info(f"Raw enrolled users data for course {course.name}: {data}")

                # Check for Moodle API errors
                if isinstance(data, dict) and 'exception' in data:
                    _logger.error(f"Moodle API error for course {course.name}: {data.get('message', 'Unknown error')}")
                    continue

                if not isinstance(data, list):
                    _logger.warning(f"Unexpected response format for course {course.name}")
                    continue

                # Filter teachers from enrolled users
                teachers = [user for user in data if any(role['roleid'] in teacher_role_ids for role in user.get('roles', []))]
                
                if not teachers:
                    _logger.warning(f"No teachers found for course {course.name}")
                    continue

                _logger.info(f"Found {len(teachers)} teachers for course {course.name}")

                for teacher in teachers:
                    # Find or create user in Odoo
                    user = request.env['res.users'].search([
                        ('moodle_id', '=', teacher['id'])
                    ])
                    
                    if not user:
                        _logger.warning(f"User with Moodle ID {teacher['id']} not found for teacher {teacher.get('fullname', 'Unknown')}")
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
                        _logger.info(f"Updated teacher record for {teacher['fullname']} in course {course.name}")
                    else:
                        request.env['moodle.course.teacher'].sudo().create(vals)
                        _logger.info(f"Created teacher record for {teacher['fullname']} in course {course.name}")

            except requests.exceptions.RequestException as e:
                _logger.error(f"HTTP Error syncing teachers for course {course.name}: {str(e)}")
                continue
            except Exception as e:
                _logger.error(f"Error syncing teachers for course {course.name}: {str(e)}")
                continue

        return 'Teacher sync completed' 