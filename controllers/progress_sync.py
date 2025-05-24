import requests
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class MoodleProgressSync(http.Controller):
    
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

    @http.route('/moodle/sync/progress', type='http', auth='user')
    def sync_progress(self, **kwargs):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            _logger.error("Moodle configuration is missing - Token or URL not found")
            return 'Moodle configuration is missing - check digi_moodle_sync.token and digi_moodle_sync.moodle_url parameters'

        _logger.info("Starting progress synchronization...")

        # Get all courses
        courses = request.env['moodle.course'].search([])
        # Get all users with moodle_id
        users = request.env['res.users'].search([('moodle_id', '!=', False)])

        if not courses:
            _logger.warning("No courses found in Odoo")
            return 'No courses found in Odoo database'
        
        if not users:
            _logger.warning("No users with Moodle ID found in Odoo")
            return 'No users with Moodle ID found in Odoo database'

        _logger.info(f"Found {len(courses)} courses and {len(users)} users to sync progress for")

        total_progress_synced = 0
        for course in courses:
            _logger.info(f"Syncing progress for course: {course.name} (ID: {course.moodle_id})")
            course_progress_synced = 0
            
            for user in users:
                params = {
                    'wstoken': config['token'],
                    'wsfunction': 'core_completion_get_activities_completion_status',
                    'courseid': course.moodle_id,
                    'userid': user.moodle_id,
                    'moodlewsrestformat': 'json'
                }

                try:
                    response = requests.get(config['url'] + '/webservice/rest/server.php', params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()

                    # Log raw response for debugging (only for first few to avoid spam)
                    if course_progress_synced < 3:
                        _logger.info(f"Raw response for user {user.name} in course {course.name}: {data}")

                    # Check for Moodle API errors
                    if 'exception' in data:
                        error_code = data.get('errorcode', 'Unknown')
                        error_message = data.get('message', 'Unknown error')
                        
                        # Skip if completion is not enabled for this course
                        if error_code in ['completionnotenabled', 'nocompletionenabled']:
                            _logger.warning(f"Completion not enabled for course {course.name} - skipping")
                            break  # Skip this course entirely
                        else:
                            _logger.error(f"Moodle API error for user {user.name} in course {course.name}: {error_message} - Code: {error_code}")
                            continue

                    if 'statuses' not in data:
                        _logger.warning(f"No completion statuses found for user {user.name} in course {course.name}")
                        continue

                    user_activities_synced = 0
                    for activity in data['statuses']:
                        vals = {
                            'userid': user.id,
                            'courseid': course.id,
                            'cmid': activity['cmid'],
                            'activity_name': activity.get('activityname', ''),
                            'completionstate': str(activity['completionstate']),
                            'timemodified': activity.get('timemodified')
                        }

                        # Create or update progress
                        progress = request.env['moodle.activity.progress'].sudo().search([
                            ('userid', '=', user.id),
                            ('courseid', '=', course.id),
                            ('cmid', '=', activity['cmid'])
                        ])

                        if progress:
                            progress.write(vals)
                            _logger.debug(f"Updated progress for activity {activity.get('activityname')} - User: {user.name}")
                        else:
                            request.env['moodle.activity.progress'].sudo().create(vals)
                            _logger.debug(f"Created progress for activity {activity.get('activityname')} - User: {user.name}")

                        user_activities_synced += 1

                    if user_activities_synced > 0:
                        _logger.info(f"Synced {user_activities_synced} activities for user {user.name} in course {course.name}")
                        course_progress_synced += user_activities_synced

                except requests.exceptions.Timeout:
                    _logger.error(f"Timeout error syncing progress for user {user.name} in course {course.name}")
                    continue
                except requests.exceptions.ConnectionError:
                    _logger.error(f"Connection error syncing progress for user {user.name} in course {course.name}")
                    continue
                except requests.exceptions.RequestException as e:
                    _logger.error(f"HTTP Error syncing progress for user {user.name} in course {course.name}: {str(e)}")
                    continue
                except Exception as e:
                    _logger.error(f"Unexpected error syncing progress for user {user.name} in course {course.name}: {str(e)}")
                    continue

            _logger.info(f"Completed course {course.name}: {course_progress_synced} progress records synced")
            total_progress_synced += course_progress_synced

        _logger.info(f"Progress synchronization completed - Total: {total_progress_synced} records synced")
        return f'Progress sync completed successfully - {total_progress_synced} records synced'