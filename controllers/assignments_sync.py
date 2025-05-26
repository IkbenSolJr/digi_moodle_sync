import requests
from odoo import http
from odoo.http import request
import logging
from datetime import datetime
from odoo.exceptions import AccessError
import json

_logger = logging.getLogger(__name__)

MOODLE_SYNC_MANAGER_GROUP = 'digi_moodle_sync.group_manager'

class MoodleAssignmentSync(http.Controller):
    
    def _check_access_rights(self):
        if not request.env.user.has_group(MOODLE_SYNC_MANAGER_GROUP):
            _logger.warning(
                f"User {request.env.user.login} (ID: {request.env.user.id}) attempt to access Moodle Assignment Sync without proper rights."
            )
            raise AccessError("Bạn không có quyền thực hiện hành động này. Vui lòng liên hệ quản trị viên.")

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
        _logger.debug(f"Moodle Config - Token: {'Found' if token else 'Missing'}, URL: {api_url if api_url else 'Missing'}")
        
        return {
            'token': token,
            'url': moodle_url,
            'api_url': api_url
        }

    @http.route('/moodle/sync/assignments', type='http', auth='user', csrf=False, methods=['GET'])
    def sync_assignments(self, **kwargs):
        _logger.info(
            f"Assignment Sync: User {request.env.user.login} (ID: {request.env.user.id}) initiated. Params: {kwargs}"
        )
        try:
            self._check_access_rights()
        except AccessError as e:
            return request.make_response(
                json.dumps({'error': str(e)}), 
                status=403, 
                headers=[('Content-Type', 'application/json')])

        config = self._get_moodle_config()
        if not config['token'] or not config['api_url']:
            _logger.error("Moodle configuration is missing - Token or URL not found")
            return request.make_response(json.dumps({'error': 'Moodle configuration is missing - check digi_moodle_sync.token and digi_moodle_sync.moodle_url parameters'}), status=503, headers=[('Content-Type', 'application/json')])

        _logger.info("Starting assignment synchronization...")
        courses = request.env['moodle.course'].search([('active','=',True)])
        if not courses:
            _logger.warning("No active courses found in Odoo to sync assignments for.")
            return request.make_response(json.dumps({'error': 'No active courses found in Odoo database'}), status=503, headers=[('Content-Type', 'application/json')])
        
        _logger.info(f"Found {len(courses)} active courses to sync assignments for.")
        total_assignments_synced = 0
        total_submissions_synced_overall = 0
        AssignmentModel = request.env['moodle.assignment'].sudo()

        for course in courses:
            _logger.info(f"Syncing assignments for course: {course.name} (Moodle Course ID: {course.moodle_id})")
            params = {
                'wstoken': config['token'],
                'wsfunction': 'mod_assign_get_assignments',
                'courseids[]': course.moodle_id,
                'moodlewsrestformat': 'json'
            }
            try:
                response = requests.get(config['api_url'], params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict) and 'exception' in data:
                    _logger.error(f"Moodle API error for course {course.name}: {data.get('message', 'Unknown error')} - Code: {data.get('errorcode', 'Unknown')}")
                    continue

                if 'courses' not in data or not isinstance(data['courses'], list):
                    _logger.warning(f"No assignments found or invalid format for course {course.name}. Response: {data}")
                    continue

                assignments_in_course_api = []
                for course_data_api in data['courses']:
                    if 'assignments' in course_data_api and isinstance(course_data_api['assignments'], list):
                        assignments_in_course_api.extend(course_data_api['assignments'])
                
                if not assignments_in_course_api:
                    _logger.info(f"No assignments returned by API for course {course.name}")
                    continue

                _logger.info(f"API returned {len(assignments_in_course_api)} assignments for course {course.name}.")
                
                existing_assignments_in_course = AssignmentModel.search([('course_id', '=', course.id)])
                existing_assignments_map = {assign.moodle_id: assign for assign in existing_assignments_in_course}
                
                assignments_to_create_vals = []
                assignments_to_update_map = {}
                processed_assignment_ids_for_submission_sync = []

                for assign_data_api in assignments_in_course_api:
                    moodle_assign_id = assign_data_api.get('id')
                    if not moodle_assign_id:
                        _logger.warning(f"Assignment data from API for course {course.name} missing 'id'. Data: {assign_data_api}")
                        continue

                    vals = {
                        'moodle_id': moodle_assign_id,
                        'name': assign_data_api.get('name', 'Unnamed Assignment'),
                        'duedate': datetime.fromtimestamp(assign_data_api['duedate']) if assign_data_api.get('duedate') else False,
                        'course_id': course.id,
                        'last_sync_date': datetime.now(),
                    }
                    if moodle_assign_id in existing_assignments_map:
                        assignments_to_update_map[existing_assignments_map[moodle_assign_id].id] = vals
                        processed_assignment_ids_for_submission_sync.append(existing_assignments_map[moodle_assign_id].id)
                    else:
                        assignments_to_create_vals.append(vals)
                
                created_assignments_count = 0
                if assignments_to_create_vals:
                    try:
                        created_records = AssignmentModel.create(assignments_to_create_vals)
                        created_assignments_count = len(created_records)
                        _logger.debug(f"Batch created {created_assignments_count} assignments for course {course.name}.")
                        for rec in created_records: processed_assignment_ids_for_submission_sync.append(rec.id)
                    except Exception as e_create_batch:
                        _logger.error(f"Error batch creating assignments for course {course.name}: {e_create_batch}", exc_info=True)
                        # Fallback to individual create for robustness
                        for v_c in assignments_to_create_vals:
                            try: 
                                new_rec = AssignmentModel.create(v_c)
                                _logger.debug(f"Individually created assignment {v_c['name']} for course {course.name}.")
                                created_assignments_count+=1
                                processed_assignment_ids_for_submission_sync.append(new_rec.id)
                            except Exception as e_c_single:
                                _logger.error(f"Error individually creating assignment {v_c.get('name')} for course {course.name}: {e_c_single}")
                
                updated_assignments_count = 0
                for assign_id, update_vals in assignments_to_update_map.items():
                    try:
                        AssignmentModel.browse(assign_id).write(update_vals)
                        _logger.debug(f"Updated assignment ID {assign_id} in course {course.name}.")
                        updated_assignments_count += 1
                    except Exception as e_update:
                        _logger.error(f"Error updating assignment ID {assign_id} for course {course.name}: {e_update}")

                course_assignments_processed_count = created_assignments_count + updated_assignments_count
                total_assignments_synced += course_assignments_processed_count
                _logger.info(f"Processed {course_assignments_processed_count} assignments for course {course.name} (Created: {created_assignments_count}, Updated: {updated_assignments_count}).")

                # Sync submissions for all created/updated assignments in this course
                if processed_assignment_ids_for_submission_sync:
                    assignments_for_submission_sync = AssignmentModel.browse(processed_assignment_ids_for_submission_sync)
                    submissions_synced_this_course = self._sync_submissions(config, assignments_for_submission_sync)
                    total_submissions_synced_overall += submissions_synced_this_course

            except requests.exceptions.RequestException as e_req:
                _logger.error(f"API request error syncing assignments for course {course.name}: {e_req}")
            except Exception as e_course:
                _logger.error(f"Unexpected error syncing assignments for course {course.name}: {e_course}", exc_info=True)
        
        _logger.info(f"Assignment synchronization completed. Total assignments synced: {total_assignments_synced}, Total submissions synced: {total_submissions_synced_overall}.")
        return request.make_response(json.dumps({
            'message': f'Assignment sync completed successfully. Assignments: {total_assignments_synced}, Submissions: {total_submissions_synced_overall}.'
        }), headers=[('Content-Type', 'application/json')])

    def _sync_submissions(self, config, assignments_to_sync):
        _logger.info(f"Starting submission sync for {len(assignments_to_sync)} assignments.")
        if not assignments_to_sync:
            return 0

        SubmissionModel = request.env['moodle.assignment.submission'].sudo()
        ResUsers = request.env['res.users'].sudo()
        MoodleUser = request.env['moodle.user'].sudo()
        total_submissions_processed_count = 0

        # API mod_assign_get_submissions expects assignmentids[]
        moodle_assignment_ids = [assign.moodle_id for assign in assignments_to_sync if assign.moodle_id]
        if not moodle_assignment_ids:
            _logger.warning("No Moodle assignment IDs found for submission sync.")
            return 0

        params = {
            'wstoken': config['token'],
            'wsfunction': 'mod_assign_get_submissions',
            'moodlewsrestformat': 'json'
        }
        # Add assignment IDs to params. API might have a limit, but typically handles many.
        for i, moodle_assign_id in enumerate(moodle_assignment_ids):
            params[f'assignmentids[{i}]'] = moodle_assign_id
        
        try:
            response = requests.get(config['api_url'], params=params, timeout=60) # Increased timeout
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and 'exception' in data:
                _logger.error(f"Moodle API error for submissions: {data.get('message', 'Unknown error')} - Code: {data.get('errorcode', 'Unknown')}")
                return 0
            
            if 'assignments' not in data or not isinstance(data['assignments'], list):
                _logger.warning(f"No submissions data or invalid format in API response. Response: {data}")
                return 0

            # Map Odoo assignment ID to Moodle assignment ID for quick lookup
            odoo_assignment_map = {assign.moodle_id: assign.id for assign in assignments_to_sync}

            submissions_to_create_vals = []
            submissions_to_update_map = {}

            for assign_data_api in data['assignments']:
                api_moodle_assignment_id = assign_data_api.get('assignmentid')
                odoo_assignment_id = odoo_assignment_map.get(api_moodle_assignment_id)
                if not odoo_assignment_id:
                    _logger.warning(f"Skipping submissions for Moodle assignment ID {api_moodle_assignment_id} as it's not in the processing list.")
                    continue

                if 'submissions' not in assign_data_api or not isinstance(assign_data_api['submissions'], list):
                    _logger.info(f"No submissions array in API data for Moodle assignment ID {api_moodle_assignment_id}.")
                    continue
                
                for sub_data_api in assign_data_api['submissions']:
                    moodle_user_id = sub_data_api.get('userid')
                    if not moodle_user_id:
                        _logger.warning(f"Submission for Moodle assignment ID {api_moodle_assignment_id} without Moodle user ID. Data: {sub_data_api}")
                        continue
                    
                    # Find Odoo user (res.users) via moodle_id
                    odoo_user = ResUsers.search([('moodle_id', '=', moodle_user_id)], limit=1)
                    if not odoo_user:
                        # Optional: Attempt to find/create moodle.user and then res.users if needed
                        _logger.warning(f"Odoo user with Moodle ID {moodle_user_id} not found for submission in Moodle assignment ID {api_moodle_assignment_id}. Consider running user sync first.")
                        continue
                    
                    submission_status_api = sub_data_api.get('status')
                    if not submission_status_api:
                         _logger.warning(f"Submission for Moodle user ID {moodle_user_id}, Moodle assignment ID {api_moodle_assignment_id} has no status. Data: {sub_data_api}")
                         continue # or set a default status

                    vals = {
                        'assignment_id': odoo_assignment_id,
                        'user_id': odoo_user.id,
                        'status': submission_status_api,
                        'timemodified': datetime.fromtimestamp(sub_data_api['timemodified']) if sub_data_api.get('timemodified') else False,
                        'grade': sub_data_api.get('grade'), # API might send grade as part of submission status or a separate grade call
                        'last_sync_date': datetime.now(),
                    }

                    existing_submission = SubmissionModel.search([
                        ('assignment_id', '=', odoo_assignment_id),
                        ('user_id', '=', odoo_user.id)
                    ], limit=1)

                    if existing_submission:
                        submissions_to_update_map[existing_submission.id] = vals
                    else:
                        submissions_to_create_vals.append(vals)
            
            created_submissions_count = 0
            if submissions_to_create_vals:
                try:
                    created_subs = SubmissionModel.create(submissions_to_create_vals)
                    created_submissions_count = len(created_subs)
                    _logger.debug(f"Batch created {created_submissions_count} submissions.")
                except Exception as e_create_batch_sub:
                    _logger.error(f"Error batch creating submissions: {e_create_batch_sub}", exc_info=True)
                    for v_s_c in submissions_to_create_vals:
                        try:
                            SubmissionModel.create(v_s_c)
                            _logger.debug(f"Individually created submission for assignment {v_s_c['assignment_id']} user {v_s_c['user_id']}.")
                            created_submissions_count +=1
                        except Exception as e_s_c_single:
                            _logger.error(f"Error individually creating submission for assignment {v_s_c.get('assignment_id')} user {v_s_c.get('user_id')}: {e_s_c_single}")
                            
            updated_submissions_count = 0
            for sub_id, update_vals_sub in submissions_to_update_map.items():
                try:
                    SubmissionModel.browse(sub_id).write(update_vals_sub)
                    _logger.debug(f"Updated submission ID {sub_id}.")
                    updated_submissions_count += 1
                except Exception as e_update_sub:
                    _logger.error(f"Error updating submission ID {sub_id}: {e_update_sub}")
            
            total_submissions_processed_count = created_submissions_count + updated_submissions_count
            _logger.info(f"Processed {total_submissions_processed_count} submissions (Created: {created_submissions_count}, Updated: {updated_submissions_count}) for the provided assignments.")

        except requests.exceptions.RequestException as e_req_sub:
            _logger.error(f"API request error syncing submissions: {e_req_sub}")
        except Exception as e_sub_main:
            _logger.error(f"Unexpected error syncing submissions: {e_sub_main}", exc_info=True)
            
        return total_submissions_processed_count