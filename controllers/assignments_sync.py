import requests
from odoo import http
from odoo.http import request
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class MoodleAssignmentSync(http.Controller):
    
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

    @http.route('/moodle/sync/assignments', type='http', auth='user')
    def sync_assignments(self, **kwargs):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            _logger.error("Moodle configuration is missing - Token or URL not found")
            return 'Moodle configuration is missing - check digi_moodle_sync.token and digi_moodle_sync.moodle_url parameters'

        _logger.info("Starting assignment synchronization...")

        # Get all courses
        courses = request.env['moodle.course'].search([])
        
        if not courses:
            _logger.warning("No courses found in Odoo")
            return 'No courses found in Odoo database'
        
        _logger.info(f"Found {len(courses)} courses to sync assignments for")
        
        for course in courses:
            _logger.info(f"Syncing assignments for course: {course.name} (ID: {course.moodle_id})")
            # Get assignments for course
            params = {
                'wstoken': config['token'],
                'wsfunction': 'mod_assign_get_assignments',
                'courseids[]': course.moodle_id,
                'moodlewsrestformat': 'json'
            }

            try:
                response = requests.get(config['api_url'], params=params, timeout=30)
                if response.status_code != 200:
                    _logger.error(f"API error: status {response.status_code}, response: {response.text[:200]}")
                    continue
                    
                response.raise_for_status()
                data = response.json()

                # Check for Moodle API errors
                if 'exception' in data:
                    _logger.error(f"Moodle API error for course {course.name}: {data.get('message', 'Unknown error')} - Code: {data.get('errorcode', 'Unknown')}")
                    continue

                if 'courses' not in data:
                    _logger.warning(f"No assignments found for course {course.name} - 'courses' key missing in response")
                    continue

                assignments_synced = 0
                for course_data in data['courses']:
                    if 'assignments' not in course_data:
                        _logger.warning(f"No assignments array in course data for {course.name}")
                        continue

                    for assignment in course_data['assignments']:
                        vals = {
                            'moodle_id': assignment['id'],
                            'name': assignment['name'],
                            'duedate': assignment.get('duedate'),
                            'course_id': course.id
                        }

                        # Create or update assignment
                        assign = request.env['moodle.assignment'].sudo().search([
                            ('moodle_id', '=', assignment['id'])
                        ], limit=1)

                        if assign:
                            assign.write(vals)
                            _logger.info(f"Updated assignment: {assignment['name']} in course {course.name}")
                        else:
                            assign = request.env['moodle.assignment'].sudo().create(vals)
                            _logger.info(f"Created assignment: {assignment['name']} in course {course.name}")

                        assignments_synced += 1

                        # Get submissions for this assignment
                        self._sync_submissions(config, assign)

                _logger.info(f"Synced {assignments_synced} assignments for course {course.name}")

            except requests.exceptions.Timeout:
                _logger.error(f"Timeout error syncing assignments for course {course.name}")
                continue
            except requests.exceptions.ConnectionError:
                _logger.error(f"Connection error syncing assignments for course {course.name}")
                continue
            except requests.exceptions.RequestException as e:
                _logger.error(f"HTTP Error syncing assignments for course {course.name}: {str(e)}")
                continue
            except Exception as e:
                _logger.error(f"Unexpected error syncing assignments for course {course.name}: {str(e)}")
                continue

        _logger.info("Assignment synchronization completed")
        return 'Assignment sync completed successfully'

    def _sync_submissions(self, config, assignment):
        _logger.info(f"Syncing submissions for assignment: {assignment.name} (ID: {assignment.moodle_id})")
        params = {
            'wstoken': config['token'],
            'wsfunction': 'mod_assign_get_submissions',
            'assignmentids[]': assignment.moodle_id,
            'moodlewsrestformat': 'json'
        }

        try:
            response = requests.get(config['api_url'], params=params, timeout=30)
            if response.status_code != 200:
                _logger.error(f"API error: status {response.status_code}, response: {response.text[:200]}")
                return
                
            response.raise_for_status()
            data = response.json()

            # Check for Moodle API errors
            if 'exception' in data:
                _logger.error(f"Moodle API error for assignment {assignment.name}: {data.get('message', 'Unknown error')} - Code: {data.get('errorcode', 'Unknown')}")
                return

            if 'assignments' not in data:
                _logger.warning(f"No submissions found for assignment {assignment.name} - 'assignments' key missing in response")
                return

            MoodleUser = request.env['moodle.user'].sudo()
            submissions_synced = 0
            for assign_data in data['assignments']:
                if 'submissions' not in assign_data:
                    _logger.warning(f"No submissions array in assignment data for {assignment.name}")
                    continue

                for submission in assign_data['submissions']:
                    moodle_user_id = submission.get('userid')
                    if not moodle_user_id:
                        _logger.warning(f"Submission without user ID in assignment {assignment.name}")
                        continue
                        
                    # Tìm hoặc tạo moodle.user
                    moodle_user = MoodleUser.search([('moodle_id', '=', moodle_user_id)], limit=1)
                    if not moodle_user:
                        # Tìm user từ res.users
                        res_user = request.env['res.users'].sudo().search([
                            ('moodle_id', '=', moodle_user_id)
                        ], limit=1)
                        if res_user:
                            # Tạo moodle.user từ res.users
                            moodle_user = MoodleUser.create({
                                'name': res_user.name,
                                'login': res_user.login,
                                'email': res_user.email or '',
                                'moodle_id': moodle_user_id,
                                'odoo_user_id': res_user.id,
                                'last_sync_date': datetime.now(),
                            })
                        else:
                            _logger.warning(f"User with Moodle ID {moodle_user_id} not found for submission in assignment {assignment.name}")
                            continue
                        
                    # Lấy Odoo user từ moodle.user hoặc trực tiếp
                    user = None
                    if moodle_user.odoo_user_id:
                        user = moodle_user.odoo_user_id
                    else:
                        user = request.env['res.users'].sudo().search([
                            ('moodle_id', '=', moodle_user_id)
                        ], limit=1)
                    
                    if not user:
                        _logger.warning(f"Cannot find or create Odoo user for Moodle ID {moodle_user_id}")
                        continue

                    vals = {
                        'assignment_id': assignment.id,
                        'user_id': user.id,
                        'status': submission['status'],
                        'timemodified': submission.get('timemodified'),
                        'grade': submission.get('grade')
                    }

                    # Create or update submission
                    sub = request.env['moodle.assignment.submission'].sudo().search([
                        ('assignment_id', '=', assignment.id),
                        ('user_id', '=', user.id)
                    ], limit=1)

                    if sub:
                        sub.write(vals)
                        _logger.info(f"Updated submission for user {user.name} in assignment {assignment.name}")
                    else:
                        request.env['moodle.assignment.submission'].sudo().create(vals)
                        _logger.info(f"Created submission for user {user.name} in assignment {assignment.name}")

                    submissions_synced += 1

            _logger.info(f"Synced {submissions_synced} submissions for assignment {assignment.name}")

        except requests.exceptions.Timeout:
            _logger.error(f"Timeout error syncing submissions for assignment {assignment.name}")
        except requests.exceptions.ConnectionError:
            _logger.error(f"Connection error syncing submissions for assignment {assignment.name}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"HTTP Error syncing submissions for assignment {assignment.name}: {str(e)}")
        except Exception as e:
            _logger.error(f"Unexpected error syncing submissions for assignment {assignment.name}: {str(e)}")