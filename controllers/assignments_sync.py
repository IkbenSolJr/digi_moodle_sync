import requests
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class MoodleAssignmentSync(http.Controller):
    
    def _get_moodle_config(self):
        params = request.env['ir.config_parameter'].sudo()
        return {
            'token': params.get_param('moodle.wstoken'),
            'url': params.get_param('moodle.url')
        }

    @http.route('/moodle/sync/assignments', type='http', auth='user')
    def sync_assignments(self, **kwargs):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get all courses
        courses = request.env['moodle.course'].search([])
        
        for course in courses:
            # Get assignments for course
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

                            # Create or update assignment
                            assign = request.env['moodle.assignment'].sudo().search([
                                ('moodle_id', '=', assignment['id'])
                            ])

                            if assign:
                                assign.write(vals)
                            else:
                                assign = request.env['moodle.assignment'].sudo().create(vals)

                            # Get submissions for this assignment
                            self._sync_submissions(config, assign)

            except Exception as e:
                _logger.error(f"Error syncing assignments for course {course.name}: {str(e)}")
                continue

        return 'Assignment sync completed'

    def _sync_submissions(self, config, assignment):
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
                        user = request.env['res.users'].search([
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

                        # Create or update submission
                        sub = request.env['moodle.assignment.submission'].sudo().search([
                            ('assignment_id', '=', assignment.id),
                            ('user_id', '=', user.id)
                        ])

                        if sub:
                            sub.write(vals)
                        else:
                            request.env['moodle.assignment.submission'].sudo().create(vals)

        except Exception as e:
            _logger.error(f"Error syncing submissions for assignment {assignment.name}: {str(e)}") 