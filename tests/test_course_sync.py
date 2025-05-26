# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from odoo.tests.common import HttpCase, tagged
from odoo.exceptions import AccessError

@tagged('-at_install', 'post_install')
class TestCourseGradeSync(HttpCase):
    def setUp(self):
        super(TestCourseGradeSync, self).setUp()
        self.env = self.env(user=self.env.ref('base.user_admin'))

        self.moodle_sync_manager_group = self.env.ref('digi_moodle_sync.group_manager', raise_if_not_found=False)
        self.test_user_no_rights = self.env['res.users'].create({
            'name': 'Course Test User No Rights',
            'login': 'course_test_no_rights',
        })
        self.odoo_user_synced = self.env['res.users'].create({
            'name': 'Odoo User Synced For Courses',
            'login': 'oodoouser_synced_courses',
            'email': 'oodoouser_synced_courses@example.com',
            'moodle_id': 501 # Moodle ID của user Odoo này
        })
        if self.moodle_sync_manager_group:
            self.odoo_user_synced.write({'groups_id': [(4, self.moodle_sync_manager_group.id)]})
        
        # moodle.user tương ứng
        self.moodle_app_user = self.env['moodle.user'].create({
            'name': self.odoo_user_synced.name,
            'moodle_id': self.odoo_user_synced.moodle_id,
            'odoo_user_id': self.odoo_user_synced.id,
            'email': self.odoo_user_synced.email
        })

        # Cấu hình System Parameters
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.moodle_url', 'https://fakemoodle.example.com')
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.token', 'faketoken123')

        # Tạo moodle.course giả lập trong Odoo mà API sẽ trả về
        self.moodle_course_odoo1 = self.env['moodle.course'].create({
            'name': 'Test Moodle Course 1 From Odoo',
            'moodle_id': 1001, # Moodle ID của khóa học
            'active': True,
        })
        self.moodle_course_odoo2 = self.env['moodle.course'].create({
            'name': 'Test Moodle Course 2 From Odoo',
            'moodle_id': 1002,
            'active': True,
        })

    def test_sync_one_course_grades_access_denied(self):
        """Test /moodle/sync_courses_grades access denied."""
        if not self.moodle_sync_manager_group:
            self.skipTest("Moodle Sync Manager group not found.")
        
        # Cần một cách để thực thi request với user không có quyền
        # Ví dụ: Patch has_group của self.test_user_no_rights
        # Hoặc nếu controller gọi self.env.user.has_group, thì patch self.env.user
        from odoo.addons.digi_moodle_sync.controllers.courses_grades_sync import MoodleCourseGradeSyncController
        controller = MoodleCourseGradeSyncController()
        original_user = self.env.user
        try:
            self.env.user = self.test_user_no_rights
            with patch('odoo.addons.digi_moodle_sync.controllers.courses_grades_sync.request.env.user', self.test_user_no_rights):
                 with self.assertRaises(AccessError):
                    controller._check_access_rights()
        finally:
            self.env.user = original_user

    def test_sync_one_course_grades_missing_param(self):
        """Test /moodle/sync_courses_grades with missing odoo_userid parameter."""
        response = self.url_open('/moodle/sync_courses_grades')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Thiếu tham số odoo_userid', response.json().get('error', ''))

    def test_sync_one_course_grades_invalid_param(self):
        """Test /moodle/sync_courses_grades with invalid odoo_userid parameter."""
        response = self.url_open('/moodle/sync_courses_grades?odoo_userid=abc')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Tham số odoo_userid không hợp lệ', response.json().get('error', ''))
        
        response = self.url_open('/moodle/sync_courses_grades?odoo_userid=0')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Odoo User ID phải là số nguyên dương', response.json().get('error', ''))

    def test_sync_one_course_grades_user_not_found(self):
        """Test /moodle/sync_courses_grades with non-existent odoo_userid."""
        response = self.url_open('/moodle/sync_courses_grades?odoo_userid=99999')
        # Status code có thể là 200 OK nhưng có error message, hoặc 404 tùy cách controller xử lý
        # Hiện tại controller trả về JSON error với status 200 cho trường hợp này.
        # Nên chuẩn hóa thành 404 hoặc 400.
        # Giả sử controller đã được sửa để trả 404:
        # self.assertEqual(response.status_code, 404) 
        # Hoặc nếu vẫn là 200 với error:
        self.assertEqual(response.status_code, 200) # Theo code hiện tại của controller
        self.assertIn('không tồn tại', response.json().get('error', ''))

    @patch('odoo.addons.digi_moodle_sync.controllers.courses_grades_sync.requests.get')
    def test_sync_one_success_create(self, mock_requests_get):
        """Test successful sync of courses and grades for one user (creation)."""
        user_to_sync = self.odoo_user_synced

        # Mock cho core_enrol_get_users_courses
        mock_courses_api_data = [
            {
                'id': self.moodle_course_odoo1.moodle_id, 
                'fullname': self.moodle_course_odoo1.name,
                'shortname': 'MC1',
                'enrolledcourses': [{'timecreated': 1670000000}]
            },
            {
                'id': self.moodle_course_odoo2.moodle_id, 
                'fullname': self.moodle_course_odoo2.name,
                'shortname': 'MC2',
                'enrolledcourses': [{'timecreated': 1670000010}]
            }
        ]
        
        # Mock cho gradereport_user_get_grade_items (cho course 1)
        mock_grades_api_data_c1 = {
            'usergrades': [{
                'courseid': self.moodle_course_odoo1.moodle_id,
                'gradeitems': [
                    {'id': 701, 'itemname': 'Quiz 1', 'itemtype': 'mod', 'itemmodule': 'quiz', 'graderaw': 85.0, 'gradedategraded': 1670000100},
                    {'id': 702, 'itemname': 'Assignment 1', 'itemtype': 'mod', 'itemmodule': 'assign', 'graderaw': None, 'gradedategraded': None}
                ]
            }]
        }
        # Mock cho gradereport_user_get_grade_items (cho course 2)
        mock_grades_api_data_c2 = {
            'usergrades': [{
                'courseid': self.moodle_course_odoo2.moodle_id,
                'gradeitems': [
                    {'id': 801, 'itemname': 'Final Exam', 'itemtype': 'course', 'graderaw': 92.5, 'gradedategraded': 1670000200}
                ]
            }]
        }

        def side_effect_requests_get(*args, **kwargs):
            params = kwargs.get('params', {})
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if params.get('wsfunction') == 'core_enrol_get_users_courses' and params.get('userid') == user_to_sync.moodle_id:
                mock_resp.json.return_value = mock_courses_api_data
            elif params.get('wsfunction') == 'gradereport_user_get_grade_items':
                if params.get('courseid') == self.moodle_course_odoo1.moodle_id:
                    mock_resp.json.return_value = mock_grades_api_data_c1
                elif params.get('courseid') == self.moodle_course_odoo2.moodle_id:
                    mock_resp.json.return_value = mock_grades_api_data_c2
                else:
                    mock_resp.json.return_value = {'usergrades': []} # Default empty for other courses
            else:
                mock_resp.status_code = 404 # Should not happen
                mock_resp.json.return_value = {'error': 'Unexpected API call in test'}
            return mock_resp
        
        mock_requests_get.side_effect = side_effect_requests_get

        response = self.url_open(f'/moodle/sync_courses_grades?odoo_userid={user_to_sync.id}')
        self.assertEqual(response.status_code, 200, response.json().get('error'))
        json_result = response.json().get('result', {})

        self.assertEqual(json_result.get('courses_processed_count'), 2)
        self.assertEqual(json_result.get('enrollments_created'), 2)
        self.assertEqual(json_result.get('enrollments_updated'), 0)
        self.assertEqual(json_result.get('grades_created'), 3) # 2 for course1, 1 for course2
        self.assertEqual(json_result.get('grades_updated'), 0)

        # Kiểm tra moodle.user.course
        user_courses = self.env['moodle.user.course'].search([
            ('moodle_user_id', '=', self.moodle_app_user.id)
        ])
        self.assertEqual(len(user_courses), 2)
        for uc in user_courses:
            self.assertIsNotNone(uc.last_sync_date)
            if uc.moodle_course_id == self.moodle_course_odoo1:
                self.assertEqual(uc.course_name, self.moodle_course_odoo1.name)
                self.assertIsNotNone(uc.enrol_date)
            elif uc.moodle_course_id == self.moodle_course_odoo2:
                self.assertEqual(uc.course_name, self.moodle_course_odoo2.name)

        # Kiểm tra moodle.user.grade
        grades_c1 = self.env['moodle.user.grade'].search([
            ('moodle_user_id', '=', self.moodle_app_user.id),
            ('moodle_course_id.moodle_course_id', '=', self.moodle_course_odoo1.id) # Quan hệ qua moodle.user.course
        ])
        self.assertEqual(len(grades_c1), 2)
        grade_quiz1 = grades_c1.filtered(lambda g: g.moodle_item_id == 701)
        self.assertTrue(grade_quiz1)
        self.assertEqual(grade_quiz1.item_name, 'Quiz 1')
        self.assertEqual(grade_quiz1.grade, 85.0)
        self.assertFalse(grade_quiz1.is_null_grade)
        self.assertIsNotNone(grade_quiz1.graded_date)
        self.assertIsNotNone(grade_quiz1.last_sync_date)

        grade_assign1 = grades_c1.filtered(lambda g: g.moodle_item_id == 702)
        self.assertTrue(grade_assign1)
        self.assertEqual(grade_assign1.item_name, 'Assignment 1')
        self.assertTrue(grade_assign1.is_null_grade)
        self.assertFalse(grade_assign1.graded_date)

        grades_c2 = self.env['moodle.user.grade'].search([
            ('moodle_user_id', '=', self.moodle_app_user.id),
            ('moodle_course_id.moodle_course_id', '=', self.moodle_course_odoo2.id)
        ])
        self.assertEqual(len(grades_c2), 1)
        grade_final = grades_c2.filtered(lambda g: g.moodle_item_id == 801)
        self.assertTrue(grade_final)
        self.assertEqual(grade_final.grade, 92.5)

    # Thêm các test case:
    # - _sync_all_courses_grades (tương tự sync_one nhưng lặp qua nhiều user)
    # - Cập nhật user.course và user.grade đã tồn tại
    # - Xử lý lỗi API cho core_enrol_get_users_courses
    # - Xử lý lỗi API cho gradereport_user_get_grade_items
    # - Trường hợp moodle.course không tồn tại trong Odoo
    # - User Odoo không có moodle_id
    # - Dữ liệu grade item từ API thiếu ID
    # - Dữ liệu grade không phải là số

if __name__ == '__main__':
    unittest.main() 