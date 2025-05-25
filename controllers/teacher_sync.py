import requests
from odoo import http
from odoo.http import request
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class MoodleTeacherSync(http.Controller):
    
    def _get_moodle_config(self):
        """Get Moodle configuration with correct parameter names"""
        params = request.env['ir.config_parameter'].sudo()
        
        # Get parameters with correct names from your system
        token = params.get_param('digi_moodle_sync.token')
        moodle_url = params.get_param('digi_moodle_sync.moodle_url')
        
        # Clean URL (remove trailing slash) and add API endpoint
        if moodle_url:
            moodle_url = moodle_url.rstrip('/')
            api_url = f"{moodle_url}/webservice/rest/server.php"
        else:
            api_url = None
        
        # Log for debugging
        _logger.info(f"Moodle Config - Token: {'Found' if token else 'Missing'}, URL: {api_url}")
        
        return {
            'token': token,
            'url': moodle_url,
            'api_url': api_url
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
                response = requests.get(config['api_url'], params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

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
                MoodleUser = request.env['moodle.user'].sudo()
                
                for teacher in teachers:
                    moodle_id = teacher.get('id')
                    if not moodle_id:
                        _logger.warning("Teacher without Moodle ID, skipping")
                        continue
                
                    # Tìm hoặc tạo moodle.user
                    moodle_user = MoodleUser.search([('moodle_id', '=', moodle_id)], limit=1)
                    if not moodle_user:
                        # Tạo moodle.user
                        moodle_user = MoodleUser.create({
                            'name': teacher.get('fullname'),
                            'login': teacher.get('username', ''),
                            'email': teacher.get('email', ''),
                            'moodle_id': moodle_id,
                            'last_sync_date': datetime.now(),
                        })
                        
                    # Tìm hoặc liên kết với res.users
                    user = request.env['res.users'].sudo().search([
                        ('moodle_id', '=', moodle_id)
                    ], limit=1)
                    
                    if not user:
                        # Tìm theo email
                        email = teacher.get('email')
                        if email:
                            user = request.env['res.users'].sudo().search([
                                ('email', '=', email)
                            ], limit=1)
                            
                            if user:
                                # Cập nhật moodle_id
                                user.write({'moodle_id': moodle_id})
                                moodle_user.write({'odoo_user_id': user.id})
                                
                    if not user and moodle_user:
                        # Tạo Odoo user từ moodle user
                        user = moodle_user.find_or_create_odoo_user()

                    if not user:
                        _logger.warning(f"Couldn't find or create user for teacher {teacher.get('fullname', 'Unknown')}")
                        continue

                    vals = {
                        'user_id': user.id,
                        'course_id': course.id,
                        'fullname': teacher.get('fullname', ''),
                        'email': teacher.get('email', '')
                    }

                    # Create or update teacher record
                    teacher_record = request.env['moodle.course.teacher'].sudo().search([
                        ('user_id', '=', user.id),
                        ('course_id', '=', course.id)
                    ], limit=1)

                    if teacher_record:
                        teacher_record.write(vals)
                        _logger.info(f"Updated teacher record for {teacher.get('fullname', '')} in course {course.name}")
                    else:
                        request.env['moodle.course.teacher'].sudo().create(vals)
                        _logger.info(f"Created teacher record for {teacher.get('fullname', '')} in course {course.name}")

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