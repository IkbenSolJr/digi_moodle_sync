import requests
from odoo import http
from odoo.http import request
import logging
from datetime import datetime
from odoo.exceptions import AccessError
import json

_logger = logging.getLogger(__name__)

MOODLE_SYNC_MANAGER_GROUP = 'digi_moodle_sync.group_manager'

class MoodleProgressSync(http.Controller):
    
    def _check_access_rights(self):
        if not request.env.user.has_group(MOODLE_SYNC_MANAGER_GROUP):
            _logger.warning(
                f"User {request.env.user.login} (ID: {request.env.user.id}) attempt to access Moodle Progress Sync without proper rights."
            )
            raise AccessError("Bạn không có quyền thực hiện hành động này. Vui lòng liên hệ quản trị viên.")

    def _get_moodle_config(self):
        """Get Moodle configuration with correct parameter names"""
        params = request.env['ir.config_parameter'].sudo()
        
        # Get parameters with correct names from your system
        token = params.get_param('digi_moodle_sync.token')
        url = params.get_param('digi_moodle_sync.moodle_url')
        
        api_url = None
        if url:
            url = url.rstrip('/')
            api_url = f"{url}/webservice/rest/server.php" # Define api_url here
        
        # Log for debugging
        _logger.debug(f"Moodle Config - Token: {'Found' if token else 'Missing'}, URL: {api_url if api_url else 'Missing'}")
        
        return {
            'token': token,
            'url': url, # Base URL
            'api_url': api_url # Full API URL
        }

    @http.route('/moodle/sync/progress', type='http', auth='user', csrf=False, methods=['GET'])
    def sync_progress(self, **kwargs):
        _logger.info(
            f"Progress Sync: User {request.env.user.login} (ID: {request.env.user.id}) initiated. Params: {kwargs}"
        )
        try:
            self._check_access_rights()
        except AccessError as e:
            return request.make_response(
                json.dumps({'error': str(e)}), 
                status=403, 
                headers=[('Content-Type', 'application/json')])

        config = self._get_moodle_config()
        if not config['token'] or not config['api_url']: # Check api_url
            _logger.error("Moodle configuration is missing - Token or URL not found")
            return request.make_response(json.dumps({'error': 'Moodle configuration is missing - check digi_moodle_sync.token and digi_moodle_sync.moodle_url parameters'}), status=503, headers=[('Content-Type', 'application/json')])

        _logger.info("Starting progress synchronization...")

        courses = request.env['moodle.course'].search([('active', '=', True)])
        if not courses:
            _logger.warning("No active courses found in Odoo to sync progress for.")
            return request.make_response(json.dumps({'error': 'No active courses found in Odoo database'}), status=503, headers=[('Content-Type', 'application/json')])

        _logger.info(f"Found {len(courses)} active courses to sync progress for.")
        total_progress_records_synced = 0
        
        ResUsers = request.env['res.users'].sudo()
        ActivityProgress = request.env['moodle.activity.progress'].sudo()

        for course in courses:
            _logger.info(f"Syncing progress for course: {course.name} (Moodle ID: {course.moodle_id})")
            
            # 1. Get enrolled users for this course
            params_enrolled_users = {
                'wstoken': config['token'],
                'wsfunction': 'core_enrol_get_enrolled_users',
                'courseid': course.moodle_id,
                'moodlewsrestformat': 'json'
            }
            enrolled_moodle_user_ids = []
            try:
                resp_users = requests.get(config['api_url'], params=params_enrolled_users, timeout=30)
                resp_users.raise_for_status()
                enrolled_users_data = resp_users.json()
                if isinstance(enrolled_users_data, list):
                    enrolled_moodle_user_ids = [u['id'] for u in enrolled_users_data if 'id' in u]
                elif isinstance(enrolled_users_data, dict) and 'exception' in enrolled_users_data:
                     _logger.error(f"Moodle API error when fetching enrolled users for course {course.name} (ID: {course.moodle_id}): {enrolled_users_data.get('message', 'Unknown error')} - Code: {enrolled_users_data.get('errorcode', 'Unknown')}")
                     continue # Skip to next course
                else:
                    _logger.warning(f"Unexpected data format for enrolled users of course {course.name}: {enrolled_users_data}")
                    continue


            except requests.exceptions.RequestException as e_users:
                _logger.error(f"API error fetching enrolled users for course {course.name} (ID: {course.moodle_id}): {e_users}")
                continue # Skip to next course
            
            if not enrolled_moodle_user_ids:
                _logger.info(f"No enrolled users found in Moodle for course: {course.name}")
                continue

            # Find corresponding Odoo users
            odoo_users_for_course = ResUsers.search([('moodle_id', 'in', enrolled_moodle_user_ids)])
            if not odoo_users_for_course:
                _logger.info(f"No Odoo users with Moodle IDs {enrolled_moodle_user_ids} found for course: {course.name}")
                continue
            
            _logger.info(f"Found {len(odoo_users_for_course)} Odoo users enrolled in course {course.name} to sync progress for.")

            course_progress_synced_count = 0
            activities_to_create_vals = []
            activities_to_update = {} # {progress_id: vals}

            for odoo_user in odoo_users_for_course:
                if not odoo_user.moodle_id: # Should not happen due to search domain
                    continue

                params_activity_status = {
                    'wstoken': config['token'],
                    'wsfunction': 'core_completion_get_activities_completion_status',
                    'courseid': course.moodle_id,
                    'userid': odoo_user.moodle_id,
                    'moodlewsrestformat': 'json'
                }

                try:
                    response = requests.get(config['api_url'], params=params_activity_status, timeout=30)
                    response.raise_for_status()
                    data = response.json()

                    if isinstance(data, dict) and 'exception' in data:
                        error_code = data.get('errorcode', 'Unknown')
                        error_message = data.get('message', 'Unknown error')
                        if error_code in ['completionnotenabled', 'nocompletionenabled']:
                            _logger.warning(f"Completion not enabled for course {course.name}. Skipping progress sync for this course.")
                            break # Break from user loop, go to next course
                        else:
                            _logger.error(f"Moodle API error for user {odoo_user.name} in course {course.name}: {error_message} - Code: {error_code}")
                            continue # Skip to next user

                    if 'statuses' not in data or not isinstance(data['statuses'], list):
                        _logger.warning(f"No completion statuses or invalid format for user {odoo_user.name} in course {course.name}. Response: {data}")
                        continue

                    for activity in data['statuses']:
                        cmid = activity.get('cmid')
                        if not cmid:
                            _logger.warning(f"Activity for user {odoo_user.name}, course {course.name} missing cmid. Data: {activity}")
                            continue
                        
                        vals = {
                            'userid': odoo_user.id,
                            'courseid': course.id,
                            'cmid': cmid,
                            'activity_name': activity.get('activityname', ''), # Moodle might not always send this
                            'completionstate': str(activity['state']), # API doc says 'state' not 'completionstate'
                            'timemodified': datetime.fromtimestamp(activity['timemodified']) if activity.get('timemodified') else False,
                            'last_sync_date': datetime.now(),
                        }
                        
                        existing_progress = ActivityProgress.search([
                            ('userid', '=', odoo_user.id),
                            ('courseid', '=', course.id),
                            ('cmid', '=', cmid)
                        ], limit=1)

                        if existing_progress:
                            activities_to_update[existing_progress.id] = vals
                        else:
                            activities_to_create_vals.append(vals)
                        
                except requests.exceptions.RequestException as e:
                    _logger.error(f"API error syncing progress for user {odoo_user.name} in course {course.name}: {e}")
                    continue # Skip to next user in this course
                except Exception as e_inner:
                    _logger.error(f"Unexpected error processing progress for user {odoo_user.name} in course {course.name}: {e_inner}", exc_info=True)
                    continue
            
            # Batch create
            if activities_to_create_vals:
                try:
                    created_progress = ActivityProgress.create(activities_to_create_vals)
                    _logger.debug(f"Batch created {len(created_progress)} activity progress records for course {course.name}.")
                    course_progress_synced_count += len(created_progress)
                except Exception as e_create_batch:
                    _logger.error(f"Error batch creating activity progress for course {course.name}: {e_create_batch}", exc_info=True)
                    # Fallback to individual create with logging if batch fails
                    for v_create in activities_to_create_vals:
                        try:
                            ActivityProgress.create(v_create)
                            _logger.debug(f"Individually created activity progress for cmid {v_create['cmid']} user {v_create['userid']} course {v_create['courseid']}.")
                            course_progress_synced_count +=1
                        except Exception as e_create_single:
                             _logger.error(f"Error individually creating activity progress for cmid {v_create['cmid']} user {v_create['userid']} course {v_create['courseid']}: {e_create_single}", exc_info=True)


            # Batch update (individual writes for now, batching updates is more complex)
            updated_count_for_course = 0
            for progress_id, update_vals in activities_to_update.items():
                try:
                    record_to_update = ActivityProgress.browse(progress_id)
                    record_to_update.write(update_vals)
                    _logger.debug(f"Updated activity progress for cmid {update_vals['cmid']} user {update_vals['userid']} course {update_vals['courseid']}.")
                    updated_count_for_course +=1
                except Exception as e_update:
                    _logger.error(f"Error updating activity progress ID {progress_id} with vals {update_vals}: {e_update}", exc_info=True)
            
            course_progress_synced_count += updated_count_for_course

            if course_progress_synced_count > 0:
                _logger.info(f"Synced {course_progress_synced_count} activity progress records for course {course.name} (Moodle ID: {course.moodle_id}).")
            total_progress_records_synced += course_progress_synced_count

        _logger.info(f"Progress synchronization completed. Total activity progress records synced: {total_progress_records_synced}.")
        return request.make_response(json.dumps({
            'message': f'Progress sync completed successfully - {total_progress_records_synced} records synced'
        }), headers=[('Content-Type', 'application/json')])