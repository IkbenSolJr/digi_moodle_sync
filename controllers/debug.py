# -*- coding: utf-8 -*-
import requests
from odoo import http
from odoo.http import request
import logging
import json

_logger = logging.getLogger(__name__)

class MoodleDebugController(http.Controller):
    
    def _get_moodle_config(self):
        params = request.env['ir.config_parameter'].sudo()
        return {
            'token': params.get_param('digi_moodle_sync.token'),
            'url': params.get_param('digi_moodle_sync.moodle_url')
        }

    @http.route('/moodle/debug/test-connection', type='http', auth='user')
    def test_connection(self, **kwargs):
        """Test basic Moodle connection and API access"""
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Test basic connection
        params = {
            'wstoken': config['token'],
            'wsfunction': 'core_webservice_get_site_info',
            'moodlewsrestformat': 'json'
        }

        try:
            response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'exception' in data:
                return f"Moodle API Error: {data.get('message', 'Unknown error')}"
            
            return f"Connection OK - Site: {data.get('sitename', 'Unknown')}, Version: {data.get('version', 'Unknown')}"
            
        except Exception as e:
            return f"Connection Failed: {str(e)}"

    @http.route('/moodle/debug/available-functions', type='http', auth='user')
    def check_available_functions(self, **kwargs):
        """Check which web service functions are available"""
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get available functions
        params = {
            'wstoken': config['token'],
            'wsfunction': 'core_webservice_get_site_info',
            'moodlewsrestformat': 'json'
        }

        try:
            response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'exception' in data:
                return f"Error: {data.get('message', 'Unknown error')}"
            
            functions = data.get('functions', [])
            
            # Check specific functions we need
            required_functions = [
                'mod_assign_get_assignments',
                'mod_assign_get_submissions', 
                'core_completion_get_activities_completion_status',
                'core_enrol_get_enrolled_users'
            ]
            
            result = "Available Functions Check:\n\n"
            for func in required_functions:
                available = any(f['name'] == func for f in functions)
                result += f"- {func}: {'✓ Available' if available else '✗ Not Available'}\n"
            
            return result
            
        except Exception as e:
            return f"Error checking functions: {str(e)}"

    @http.route('/moodle/debug/test-assignments', type='http', auth='user') 
    def test_assignments(self, **kwargs):
        """Test assignments API with detailed logging"""
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get first course for testing
        course = request.env['moodle.course'].search([], limit=1)
        if not course:
            return 'No courses found in Odoo'

        _logger.info(f"Testing assignments for course: {course.name} (ID: {course.moodle_id})")
        
        params = {
            'wstoken': config['token'],
            'wsfunction': 'mod_assign_get_assignments',
            'courseids[]': course.moodle_id,
            'moodlewsrestformat': 'json'
        }

        try:
            response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
            _logger.info(f"Response status: {response.status_code}")
            _logger.info(f"Response headers: {dict(response.headers)}")
            
            response.raise_for_status()
            data = response.json()
            
            _logger.info(f"Raw response: {json.dumps(data, indent=2)}")
            
            if 'exception' in data:
                return f"Moodle API Error: {data.get('message', 'Unknown error')}\nError Code: {data.get('errorcode', 'Unknown')}"
            
            if 'courses' not in data:
                return f"No 'courses' key in response. Response keys: {list(data.keys())}"
            
            course_count = len(data['courses'])
            assignment_count = 0
            
            for course_data in data['courses']:
                if 'assignments' in course_data:
                    assignment_count += len(course_data['assignments'])
            
            return f"Success! Found {course_count} courses with {assignment_count} total assignments"
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"HTTP Error: {str(e)}")
            return f"HTTP Error: {str(e)}"
        except Exception as e:
            _logger.error(f"Error: {str(e)}")
            return f"Error: {str(e)}"

    @http.route('/moodle/debug/test-completion', type='http', auth='user')
    def test_completion(self, **kwargs):
        """Test completion tracking API"""
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get first course and user for testing
        course = request.env['moodle.course'].search([], limit=1)
        user = request.env['res.users'].search([('moodle_id', '!=', False)], limit=1)
        
        if not course or not user:
            return 'No courses or users found for testing'

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
            
            _logger.info(f"Completion response: {json.dumps(data, indent=2)}")
            
            if 'exception' in data:
                return f"Moodle API Error: {data.get('message', 'Unknown error')}\nError Code: {data.get('errorcode', 'Unknown')}"
            
            if 'statuses' not in data:
                return f"No 'statuses' key in response. Response keys: {list(data.keys())}"
            
            status_count = len(data['statuses'])
            return f"Success! Found {status_count} activity completion statuses for user {user.name} in course {course.name}"
            
        except Exception as e:
            return f"Error: {str(e)}"

    @http.route('/moodle/debug/check-course-settings', type='http', auth='user')
    def check_course_settings(self, **kwargs):
        """Check course completion settings"""
        config = self._get_moodle_config()
        if not config['token'] or not config['url']:
            return 'Moodle configuration is missing'

        # Get course info to check completion settings
        course = request.env['moodle.course'].search([], limit=1)
        if not course:
            return 'No courses found'

        params = {
            'wstoken': config['token'],
            'wsfunction': 'core_course_get_courses_by_field',
            'field': 'id',
            'value': course.moodle_id,
            'moodlewsrestformat': 'json'
        }

        try:
            response = requests.get(config['url'] + '/webservice/rest/server.php', params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'exception' in data:
                return f"Error: {data.get('message')}"
            
            if 'courses' not in data or not data['courses']:
                return "Course not found"
            
            course_info = data['courses'][0]
            completion_enabled = course_info.get('enablecompletion', 0)
            
            result = f"Course: {course_info.get('fullname', 'Unknown')}\n"
            result += f"Completion Enabled: {'Yes' if completion_enabled else 'No'}\n"
            result += f"Course Format: {course_info.get('format', 'Unknown')}\n"
            
            return result
            
        except Exception as e:
            return f"Error: {str(e)}"