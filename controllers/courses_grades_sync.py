# -*- coding: utf-8 -*-
import logging
import requests
import json
from datetime import datetime

from odoo import http
from odoo.http import request
from odoo.tools import float_is_zero # For comparing float grades if needed
from odoo.exceptions import AccessError # Added AccessError

_logger = logging.getLogger(__name__)

MOODLE_SYNC_MANAGER_GROUP = 'digi_moodle_sync.group_manager' # Define group name

class MoodleCourseGradeSyncController(http.Controller):

    def _check_access_rights(self):
        if not request.env.user.has_group(MOODLE_SYNC_MANAGER_GROUP):
            _logger.warning(
                f"User {request.env.user.login} (ID: {request.env.user.id}) attempt to access Moodle Course/Grade Sync without proper rights."
            )
            raise AccessError("Bạn không có quyền thực hiện hành động này. Vui lòng liên hệ quản trị viên.")

    def _get_moodle_api_url(self, base_url):
        if not base_url:
            return None
        return base_url.rstrip('/') + '/webservice/rest/server.php'

    @http.route('/moodle/sync_all_courses_grades', type='http', auth='user', methods=['GET'], csrf=False)
    def sync_all(self, **kw):
        _logger.info(
            f"Course/Grade Sync All: User {request.env.user.login} (ID: {request.env.user.id}) initiated. Params: {kw}"
        )
        try:
            self._check_access_rights()
        except AccessError as e:
            return request.make_response(
                json.dumps({'error': str(e)}), 
                status=403, 
                headers=[('Content-Type', 'application/json')])

        config = request.env['ir.config_parameter'].sudo()
        base_moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token = config.get_param('digi_moodle_sync.token')

        if not base_moodle_url or not token:
            _logger.error("Moodle URL hoặc Token chưa được cấu hình trong Cài đặt Hệ thống.")
            return request.make_response(json.dumps({'error': 'Moodle URL/Token chưa cấu hình.'}), headers=[('Content-Type', 'application/json')])

        api_url = self._get_moodle_api_url(base_moodle_url)
        users_to_sync = request.env['res.users'].sudo().search([('moodle_id', '!=', False), ('moodle_id', '!=', 0)])
        
        if not users_to_sync:
            _logger.info("Không tìm thấy người dùng Odoo nào có Moodle ID để đồng bộ điểm.")
            return request.make_response(json.dumps({'message': 'Không có người dùng nào có Moodle ID hợp lệ để đồng bộ.'}), headers=[('Content-Type', 'application/json')])

        _logger.info(f"Bắt đầu đồng bộ khóa học và điểm cho {len(users_to_sync)} người dùng Odoo có Moodle ID.")
        
        results = {}
        grand_total_courses_processed = 0
        grand_total_grades_created = 0
        grand_total_grades_updated = 0
        grand_total_enrollments_created = 0
        grand_total_enrollments_updated = 0

        for odoo_user in users_to_sync:
            if not odoo_user.moodle_id: # Double check
                _logger.warning(f"Người dùng Odoo {odoo_user.name} (ID: {odoo_user.id}) không có Moodle ID. Bỏ qua.")
                continue
            try:
                _logger.info(f"Đang đồng bộ cho người dùng: {odoo_user.name} (Moodle ID: {odoo_user.moodle_id})")
                sync_result = self._sync_user_courses_and_grades(odoo_user, api_url, token)
                results[odoo_user.id] = sync_result
                grand_total_courses_processed += sync_result.get('courses_processed_count', 0)
                grand_total_grades_created += sync_result.get('grades_created', 0)
                grand_total_grades_updated += sync_result.get('grades_updated', 0)
                grand_total_enrollments_created += sync_result.get('enrollments_created', 0)
                grand_total_enrollments_updated += sync_result.get('enrollments_updated', 0)

            except Exception as e:
                error_msg = f"Lỗi nghiêm trọng khi đồng bộ cho người dùng {odoo_user.name} (Moodle ID: {odoo_user.moodle_id}): {e}"
                _logger.error(error_msg, exc_info=True)
                results[odoo_user.id] = {'error': error_msg}

        final_summary_message = (
            f"Hoàn tất đồng bộ cho tất cả người dùng. "
            f"Tổng khóa học đã xử lý: {grand_total_courses_processed}. "
            f"Tổng ghi danh tạo mới: {grand_total_enrollments_created}, cập nhật: {grand_total_enrollments_updated}. "
            f"Tổng điểm tạo mới: {grand_total_grades_created}, cập nhật: {grand_total_grades_updated}."
        )
        _logger.info(final_summary_message)
        config.set_param('digi_moodle_sync.last_grades_sync_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        return request.make_response(
            json.dumps({'message': final_summary_message, 'details_per_user': results}),
            headers=[('Content-Type', 'application/json')])

    @http.route('/moodle/sync_courses_grades', type='http', auth='user', methods=['GET'], csrf=False)
    def sync_one(self, **kw):
        _logger.info(
            f"Course/Grade Sync One: User {request.env.user.login} (ID: {request.env.user.id}) initiated. Params: {kw}"
        )
        try:
            self._check_access_rights()
        except AccessError as e:
            return request.make_response(
                json.dumps({'error': str(e)}), 
                status=403, 
                headers=[('Content-Type', 'application/json')])
        
        # Validate odoo_userid parameter
        odoo_user_id_param = kw.get('odoo_userid')
        if not odoo_user_id_param:
            _logger.error("Tham số 'odoo_userid' bị thiếu.")
            return request.make_response(json.dumps({'error': 'Thiếu tham số odoo_userid (Odoo User ID).'}), status=400, headers=[('Content-Type', 'application/json')])
        try:
            odoo_user_id_int = int(odoo_user_id_param)
            if odoo_user_id_int <= 0:
                 raise ValueError("Odoo User ID phải là số nguyên dương.")
        except ValueError as ve:
            _logger.error(f"Tham số 'odoo_userid' không hợp lệ: {odoo_user_id_param}. Lỗi: {ve}")
            return request.make_response(json.dumps({'error': f'Tham số odoo_userid không hợp lệ: {ve}'}), status=400, headers=[('Content-Type', 'application/json')])

        config = request.env['ir.config_parameter'].sudo()
        base_moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token = config.get_param('digi_moodle_sync.token')

        if not base_moodle_url or not token:
            _logger.error("Moodle URL hoặc Token chưa được cấu hình.")
            return request.make_response(json.dumps({'error': 'Moodle URL/Token chưa cấu hình.'}), headers=[('Content-Type', 'application/json')])
        api_url = self._get_moodle_api_url(base_moodle_url)

        try:
            odoo_user = request.env['res.users'].sudo().browse(odoo_user_id_int)
            if not odoo_user.exists():
                return request.make_response(json.dumps({'error': f'Người dùng Odoo với ID {odoo_user_id_int} không tồn tại.'}), headers=[('Content-Type', 'application/json')])
            if not odoo_user.moodle_id:
                return request.make_response(json.dumps({'error': f'Người dùng Odoo {odoo_user.name} (ID: {odoo_user_id_int}) không có Moodle ID.'}), headers=[('Content-Type', 'application/json')])

            _logger.info(f"Bắt đầu đồng bộ khóa học và điểm cho người dùng: {odoo_user.name} (Moodle ID: {odoo_user.moodle_id})")
            data = self._sync_user_courses_and_grades(odoo_user, api_url, token)
            return request.make_response(json.dumps({'message': 'Đồng bộ hoàn tất.', 'result': data}), headers=[('Content-Type', 'application/json')])
        except Exception as e:
            _logger.error(f"Lỗi khi đồng bộ cho người dùng Odoo ID {odoo_user_id_param}: {e}", exc_info=True)
            return request.make_response(json.dumps({'error': str(e)}), status=500, headers=[('Content-Type', 'application/json')])

    def _sync_user_courses_and_grades(self, odoo_user_record, api_url, token):
        user_moodle_id = odoo_user_record.moodle_id
        odoo_user_id_int = odoo_user_record.id
        _logger.info(f"Đang xử lý người dùng: {odoo_user_record.name} (Odoo ID: {odoo_user_id_int}, Moodle ID: {user_moodle_id})")

        MoodleAppUser = request.env['moodle.user'].sudo()
        moodle_app_user = MoodleAppUser.search([('moodle_id', '=', user_moodle_id)], limit=1)
        if not moodle_app_user:
            moodle_app_user_vals = {
                'name': odoo_user_record.name,
                'login': odoo_user_record.login or f'user_{user_moodle_id}@placeholder.com',
                'email': odoo_user_record.email or f'user_{user_moodle_id}@placeholder.com',
                'moodle_id': user_moodle_id,
                'odoo_user_id': odoo_user_id_int,
                'last_sync_date': datetime.now(),
            }
            try:
                moodle_app_user = MoodleAppUser.create(moodle_app_user_vals)
                _logger.debug(f"Đã tạo moodle.user (ID: {moodle_app_user.id}) cho Moodle ID {user_moodle_id}.")
            except Exception as e_create_mu:
                _logger.error(f"Không thể tạo moodle.user cho {odoo_user_record.name} (Moodle ID {user_moodle_id}). Lỗi: {e_create_mu}")
                return {'error': f"Không thể tạo moodle.user: {e_create_mu}"}
        elif not moodle_app_user.odoo_user_id or moodle_app_user.odoo_user_id.id != odoo_user_id_int:
            try:
                moodle_app_user.write({'odoo_user_id': odoo_user_id_int, 'last_sync_date': datetime.now()})
                _logger.debug(f"Cập nhật odoo_user_id trên moodle.user (ID: {moodle_app_user.id}) thành {odoo_user_id_int}.")
            except Exception as e_write_mu:
                 _logger.error(f"Không thể cập nhật odoo_user_id trên moodle.user cho {odoo_user_record.name}. Lỗi: {e_write_mu}")
                 # Continue with existing moodle_app_user if link update fails

        params_courses = {
            'wstoken': token,
            'wsfunction': 'core_enrol_get_users_courses',
            'moodlewsrestformat': 'json',
            'userid': user_moodle_id
        }
        _logger.debug(f"Gọi API Moodle lấy DS khóa học cho User Moodle ID: {user_moodle_id}")
        try:
            r_courses = requests.get(api_url, params=params_courses, timeout=30)
            r_courses.raise_for_status()
            courses_data_api = r_courses.json() or []
        except requests.RequestException as e_req_course:
            _logger.error(f"Lỗi API (core_enrol_get_users_courses) cho Moodle User ID {user_moodle_id}: {e_req_course}")
            return {'error': f'Lỗi API lấy khóa học: {e_req_course}', 'courses_processed_count': 0, 'enrollments_created': 0, 'enrollments_updated': 0, 'grades_created': 0, 'grades_updated': 0}
        except json.JSONDecodeError as e_json_course:
            _logger.error(f"Lỗi giải mã JSON (core_enrol_get_users_courses) cho Moodle User ID {user_moodle_id}. Phản hồi: {r_courses.text[:200]}")
            return {'error': f'Lỗi JSON lấy khóa học: {e_json_course}', 'courses_processed_count': 0, 'enrollments_created': 0, 'enrollments_updated': 0, 'grades_created': 0, 'grades_updated': 0}

        _logger.info(f"API trả về {len(courses_data_api)} khóa học cho người dùng {odoo_user_record.name}.")
        if not courses_data_api:
            return {'message': 'Người dùng này không tham gia khóa học nào trên Moodle.', 'courses_processed_count': 0, 'enrollments_created': 0, 'enrollments_updated': 0, 'grades_created': 0, 'grades_updated': 0}

        UserCourseModel = request.env['moodle.user.course'].sudo()
        GradeModel = request.env['moodle.user.grade'].sudo()
        OdooCourseModel = request.env['moodle.course'].sudo()

        user_courses_to_create_vals = []
        user_courses_to_update_map = {}
        processed_user_course_records_for_grades = [] # List of moodle.user.course records

        num_enrollments_created = 0
        num_enrollments_updated = 0
        num_grades_created = 0
        num_grades_updated = 0

        for c_moodle_data in courses_data_api:
            moodle_course_id_api = c_moodle_data.get('id')
            if not moodle_course_id_api:
                _logger.warning(f"Dữ liệu khóa học từ Moodle thiếu 'id' cho user {user_moodle_id}. Data: {c_moodle_data}")
                continue

            odoo_moodle_course = OdooCourseModel.search([('moodle_id', '=', moodle_course_id_api)], limit=1)
            if not odoo_moodle_course:
                _logger.warning(f"Không tìm thấy bản ghi moodle.course trong Odoo cho Moodle Course ID: {moodle_course_id_api}. Bỏ qua khóa học này cho người dùng {user_moodle_id}. Đồng bộ khóa học trước.")
                continue 
            
            user_course_vals = {
                'moodle_course_id': odoo_moodle_course.id, 
                'moodle_user_id': moodle_app_user.id,
                'course_name': c_moodle_data.get('fullname', 'Khóa học không tên từ API'),
                'course_shortname': c_moodle_data.get('shortname', ''),
                'enrol_date': datetime.fromtimestamp(c_moodle_data['enrolledcourses'][0]['timecreated']) if c_moodle_data.get('enrolledcourses') and c_moodle_data['enrolledcourses'] and c_moodle_data['enrolledcourses'][0].get('timecreated') else False,
                'last_sync_date': datetime.now(),
            }
            
            existing_user_course_record = UserCourseModel.search([
                ('moodle_course_id', '=', odoo_moodle_course.id),
                ('moodle_user_id', '=', moodle_app_user.id)
            ], limit=1)

            if not existing_user_course_record:
                user_courses_to_create_vals.append(user_course_vals)
            else:
                user_courses_to_update_map[existing_user_course_record.id] = user_course_vals
                processed_user_course_records_for_grades.append(existing_user_course_record)

        if user_courses_to_create_vals:
            try:
                created_enrollments = UserCourseModel.create(user_courses_to_create_vals)
                num_enrollments_created = len(created_enrollments)
                _logger.debug(f"Batch created {num_enrollments_created} moodle.user.course records for user {odoo_user_record.name}.")
                processed_user_course_records_for_grades.extend(created_enrollments)
            except Exception as e_batch_create_uc:
                _logger.error(f"Lỗi batch create moodle.user.course cho user {odoo_user_record.name}: {e_batch_create_uc}", exc_info=True)
                # Fallback
                for val_uc in user_courses_to_create_vals:
                    try: 
                        new_uc = UserCourseModel.create(val_uc)
                        _logger.debug(f"Individually created moodle.user.course for user {odoo_user_record.name}, course {val_uc['course_name']}.")
                        num_enrollments_created += 1
                        processed_user_course_records_for_grades.append(new_uc)
                    except Exception as e_single_uc:
                         _logger.error(f"Lỗi tạo moodle.user.course cho user {odoo_user_record.name}, course {val_uc.get('course_name')}: {e_single_uc}")

        for rec_id, update_vals in user_courses_to_update_map.items():
            try:
                UserCourseModel.browse(rec_id).write(update_vals)
                num_enrollments_updated += 1
                _logger.debug(f"Updated moodle.user.course ID {rec_id} for user {odoo_user_record.name}.")
            except Exception as e_update_uc:
                _logger.error(f"Lỗi cập nhật moodle.user.course ID {rec_id} cho user {odoo_user_record.name}: {e_update_uc}")

        # Sync grades for processed user_course_records
        grades_to_create_vals = []
        grades_to_update_map = {}

        for user_course_record in processed_user_course_records_for_grades:
            # Ensure moodle_course_id on user_course_record.moodle_course_id is the odoo moodle.course record.
            # And we need moodle_id from that odoo_moodle_course for the API call.
            odoo_course_for_grade = user_course_record.moodle_course_id 
            if not odoo_course_for_grade or not odoo_course_for_grade.moodle_id:
                _logger.warning(f"Skipping grade sync for user_course {user_course_record.id} as linked odoo_moodle_course or its moodle_id is missing.")
                continue
            
            api_course_id_for_grades = odoo_course_for_grade.moodle_id

            params_grades = {
                'wstoken': token,
                'wsfunction': 'gradereport_user_get_grade_items',
                'moodlewsrestformat': 'json',
                'userid': user_moodle_id, 
                'courseid': api_course_id_for_grades
            }
            _logger.debug(f"Gọi API Moodle lấy điểm cho User Moodle ID {user_moodle_id}, Course Moodle ID {api_course_id_for_grades}")
            try:
                r_grades = requests.get(api_url, params=params_grades, timeout=30)
                r_grades.raise_for_status()
                grades_report_data = r_grades.json() or {}
            except requests.RequestException as e_req_grade:
                _logger.error(f"Lỗi API (gradereport_user_get_grade_items) cho User {user_moodle_id}, Course {api_course_id_for_grades}: {e_req_grade}")
                continue 
            except json.JSONDecodeError as e_json_grade:
                _logger.error(f"Lỗi giải mã JSON (gradereport_user_get_grade_items) cho User {user_moodle_id}, Course {api_course_id_for_grades}. Phản hồi: {r_grades.text[:200]}")
                continue

            if 'usergrades' in grades_report_data and isinstance(grades_report_data['usergrades'], list):
                for ug_item in grades_report_data['usergrades']:
                    if 'gradeitems' in ug_item and isinstance(ug_item['gradeitems'], list):
                        for grade_item_api_data in ug_item['gradeitems']:
                            processed_grade_info = self._prepare_grade_vals(grade_item_api_data, moodle_app_user.id, user_course_record.id)
                            if processed_grade_info:
                                grade_vals_for_db = processed_grade_info['data']
                                existing_grade_rec = GradeModel.search([
                                    ('moodle_user_id', '=', moodle_app_user.id),
                                    ('moodle_course_id', '=', user_course_record.id),
                                    ('moodle_item_id', '=', grade_vals_for_db['moodle_item_id'])
                                ], limit=1)
                                if existing_grade_rec:
                                    grades_to_update_map[existing_grade_rec.id] = grade_vals_for_db
                                else:
                                    grades_to_create_vals.append(grade_vals_for_db)
            else:
                _logger.info(f"Không có 'usergrades' trong phản hồi điểm cho user {user_moodle_id}, course {api_course_id_for_grades}. Phản hồi: {grades_report_data}")

        if grades_to_create_vals:
            try:
                created_grades = GradeModel.create(grades_to_create_vals)
                num_grades_created = len(created_grades)
                _logger.debug(f"Batch created {num_grades_created} moodle.user.grade records for user {odoo_user_record.name}.")
            except Exception as e_batch_create_g:
                _logger.error(f"Lỗi batch create moodle.user.grade cho user {odoo_user_record.name}: {e_batch_create_g}", exc_info=True)
                for val_g in grades_to_create_vals:
                    try: 
                        GradeModel.create(val_g)
                        _logger.debug(f"Individually created grade for item {val_g['item_name']} user {odoo_user_record.name}.")
                        num_grades_created+=1
                    except Exception as e_single_g:
                         _logger.error(f"Lỗi tạo grade cho item {val_g.get('item_name')} user {odoo_user_record.name}: {e_single_g}")

        for rec_id, update_vals in grades_to_update_map.items():
            try:
                GradeModel.browse(rec_id).write(update_vals)
                num_grades_updated += 1
                _logger.debug(f"Updated moodle.user.grade ID {rec_id} for user {odoo_user_record.name}.")
            except Exception as e_update_g:
                _logger.error(f"Lỗi cập nhật moodle.user.grade ID {rec_id} cho user {odoo_user_record.name}: {e_update_g}")
        
        _logger.info(f"Hoàn tất xử lý khóa học và điểm cho User {odoo_user_record.name}. Ghi danh mới: {num_enrollments_created}, cập nhật: {num_enrollments_updated}. Điểm mới: {num_grades_created}, cập nhật: {num_grades_updated}.")
        return {
            'courses_processed_count': len(courses_data_api),
            'enrollments_created': num_enrollments_created,
            'enrollments_updated': num_enrollments_updated,
            'grades_created': num_grades_created,
            'grades_updated': num_grades_updated
        }

    def _prepare_grade_vals(self, grade_item_api_data, moodle_app_user_pk, user_course_pk):
        moodle_grade_item_id = grade_item_api_data.get('id')
        if not moodle_grade_item_id:
            _logger.warning(f"Mục điểm từ Moodle API thiếu 'id'. Bỏ qua. Data: {grade_item_api_data}")
            return None

        item_name = grade_item_api_data.get('itemname') or 'Không tên'
        raw_grade = grade_item_api_data.get('graderaw') # graderaw is typically the numeric grade
        
        is_null_grade_flag = raw_grade is None 
        grade_value_float = 0.0

        if raw_grade is not None:
            try:
                grade_value_float = float(raw_grade)
            except ValueError:
                _logger.debug(f"Giá trị điểm '{raw_grade}' (item: {item_name}, id: {moodle_grade_item_id}) không phải là số. Sẽ được coi là is_null_grade=True.")
                is_null_grade_flag = True
        
        gradedate_ts = grade_item_api_data.get('gradedategraded') # API usually sends this as 'gradedategraded'
        graded_date_dt = datetime.fromtimestamp(gradedate_ts) if gradedate_ts else False

        grade_record_vals = {
            'grade': grade_value_float, 
            'is_null_grade': is_null_grade_flag,
            'graded_date': graded_date_dt, 
            'item_name': item_name,
            'item_type': grade_item_api_data.get('itemtype'),
            'item_module': grade_item_api_data.get('itemmodule'),
            'moodle_user_id': moodle_app_user_pk,
            'moodle_course_id': user_course_pk,
            'moodle_item_id': moodle_grade_item_id,
            'last_sync_date': datetime.now(),
        }
        return {'data': grade_record_vals} # Removed 'status' as it's determined by caller
