import requests
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class MoodleProgressSync(http.Controller):
    
    def _get_moodle_config(self):
        params = request.env['ir.config_parameter'].sudo()
        return {
            'token': params.get_param('moodle.wstoken'),
            'url': params.get_param('moodle.url')
        }

    @http.route('/moodle/sync/progress', type='http', auth='user')
    def sync_progress(self, **kwargs):
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get all courses
        courses = request.env['moodle.course'].search([])
        # Get all users
        users = request.env['res.users'].search([('moodle_id', '!=', False)])

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

                            # Create or update progress
                            progress = request.env['moodle.activity.progress'].sudo().search([
                                ('userid', '=', user.id),
                                ('courseid', '=', course.id),
                                ('cmid', '=', activity['cmid'])
                            ])

                            if progress:
                                progress.write(vals)
                            else:
                                request.env['moodle.activity.progress'].sudo().create(vals)

                except Exception as e:
                    _logger.error(f"Error syncing progress for user {user.name} in course {course.name}: {str(e)}")
                    continue

        return 'Progress sync completed' 