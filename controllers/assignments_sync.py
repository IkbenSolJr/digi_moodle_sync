import requests
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class MoodleAssignmentSync(http.Controller):
    
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
                response = requests.get(config['url'] + '/webservice/rest/server.php', params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                # Log raw response for debugging
                _logger.info(f"Raw assignment data for course {course.name}: {data}")

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
                        ])

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
            response = requests.get(config['url'] + '/webservice/rest/server.php', params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Log raw response for debugging
            _logger.info(f"Raw submission data for assignment {assignment.name}: {data}")

            # Check for Moodle API errors
            if 'exception' in data:
                _logger.error(f"Moodle API error for assignment {assignment.name}: {data.get('message', 'Unknown error')} - Code: {data.get('errorcode', 'Unknown')}")
                return

            if 'assignments' not in data:
                _logger.warning(f"No submissions found for assignment {assignment.name} - 'assignments' key missing in response")
                return

            submissions_synced = 0
            for assign_data in data['assignments']:
                if 'submissions' not in assign_data:
                    _logger.warning(f"No submissions array in assignment data for {assignment.name}")
                    continue

                for submission in assign_data['submissions']:
                    user = request.env['res.users'].search([
                        ('moodle_id', '=', submission['userid'])
                    ])
                    if not user:
                        _logger.warning(f"User with Moodle ID {submission['userid']} not found for submission in assignment {assignment.name}")
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
                    ])

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