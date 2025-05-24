import requests
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class MoodleTeacherSync(http.Controller):
    
    def _get_moodle_config(self):
        """Get Moodle configuration with correct parameter names"""
        params = request.env['ir.config_parameter'].sudo()
        
        # Get parameters with correct names from your system
        token = params.get_param('digi_moodle_sync.token')
        url = params.get_param('digi_moodle_sync.moodle_url')
        
        # Clean URL (remove trailing slash)
        if url:
            url = url.rstrip('/')
        
        # Log for debugging
        _logger.info(f"Moodle Config - Token: {'Found' if token else 'Missing'}, URL: {'Found' if url else 'Missing'}")
        
        return {
            'token': token,
            'url': url
        }

    @http.route('/moodle/sync/teachers', type='http', auth='user')
    def sync_teachers(self, **kwargs):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            _logger.error("Moodle configuration is missing - Token or URL not found")
            return 'Moodle configuration is missing - check digi_moodle_sync.token and digi_moodle_sync.moodle_url parameters'

        _logger.info("Starting teacher synchronization...")

        # Get all courses
        courses = request.env['moodle.course'].search([])
        
        if not courses:
            _logger.warning("No courses found in Odoo")
            return 'No courses found in Odoo database'
        
        # Define teacher role IDs (can be configured in Moodle settings)
        teacher_role_ids = [3, 4]  # 3: Teacher, 4: Non-editing teacher
        
        _logger.info(f"Found {len(courses)} courses to sync teachers for")
        total_teachers_synced = 0
        
        for course in courses:
            _logger.info(f"Syncing teachers for course: {course.name} (ID: {course.moodle_id})")
            params = {
                'wstoken': config['token'],
                'wsfunction': 'core_enrol_get_enrolled_users',
                'courseid': course.moodle_id,
                'moodlewsrestformat': 'json'
            }

            try:
                response = requests.get(config['url'] + '/webservice/rest/server.php', params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                # Log raw response for debugging (only for first course to avoid spam)
                if total_teachers_synced == 0:
                    _logger.info(f"Raw enrolled users data for course {course.name}: {data}")

                # Check for Moodle API errors
                if isinstance(data, dict) and 'exception' in data:
                    error_code = data.get('errorcode', 'Unknown')
                    error_message = data.get('message', 'Unknown error')
                    _logger.error(f"Moodle API error for course {course.name}: {error_message} - Code: {error_code}")
                    continue

                if not isinstance(data, list):
                    _logger.warning(f"Unexpected response format for course {course.name} - expected list, got {type(data)}")
                    continue

                # Filter teachers from enrolled users
                teachers = []
                for user in data:
                    user_roles = user.get('roles', [])
                    if any(role['roleid'] in teacher_role_ids for role in user_roles):
                        teachers.append(user)
                
                if not teachers:
                    _logger.warning(f"No teachers found for course {course.name}")
                    continue

                _logger.info(f"Found {len(teachers)} teachers for course {course.name}")

                course_teachers_synced = 0
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

                    course_teachers_synced += 1

                _logger.info(f"Synced {course_teachers_synced} teachers for course {course.name}")
                total_teachers_synced += course_teachers_synced

            except requests.exceptions.Timeout:
                _logger.error(f"Timeout error syncing teachers for course {course.name}")
                continue
            except requests.exceptions.ConnectionError:
                _logger.error(f"Connection error syncing teachers for course {course.name}")
                continue
            except requests.exceptions.RequestException as e:
                _logger.error(f"HTTP Error syncing teachers for course {course.name}: {str(e)}")
                continue
            except Exception as e:
                _logger.error(f"Unexpected error syncing teachers for course {course.name}: {str(e)}")
                continue

        _logger.info(f"Teacher synchronization completed - Total: {total_teachers_synced} teachers synced")
        return f'Teacher sync completed successfully - {total_teachers_synced} teachers synced'