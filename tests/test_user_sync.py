# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock

from odoo.tests.common import HttpCase, tagged
from odoo.exceptions import AccessError

# Giả sử controller và group name đã được định nghĩa và có thể import
# from odoo.addons.digi_moodle_sync.controllers.users_sync import MoodleUserSyncController, MOODLE_SYNC_MANAGER_GROUP

@tagged('-at_install', 'post_install')
class TestUserSync(HttpCase):
    def setUp(self):
        super(TestUserSync, self).setUp()
        self.env = self.env(user=self.env.ref('base.user_admin')) # Chạy test với admin
        # Tạo user test và group nếu cần
        self.test_user_no_rights = self.env['res.users'].create({
            'name': 'Test User No Rights',
            'login': 'test_user_no_rights',
            'email': 'test_user_no_rights@example.com',
        })
        self.moodle_sync_manager_group = self.env.ref('digi_moodle_sync.group_manager', raise_if_not_found=False)
        if not self.moodle_sync_manager_group:
            # Nếu group chưa tồn tại, có thể tạo nó ở đây hoặc bỏ qua một số test liên quan đến quyền
            pass 
            
        self.user_with_rights = self.env['res.users'].create({
            'name': 'Test User With Rights',
            'login': 'test_user_with_rights',
            'email': 'test_user_with_rights@example.com',
            'groups_id': [(6, 0, [self.moodle_sync_manager_group.id])] if self.moodle_sync_manager_group else []
        })

        # Cấu hình System Parameters giả lập
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.moodle_url', 'https://fakemoodle.example.com')
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.token', 'faketoken123')

    def test_sync_users_access_denied(self):
        """Test sync_users endpoint access denied for user without rights."""
        if not self.moodle_sync_manager_group: 
            self.skipTest("Moodle Sync Manager group not found, skipping permission test.")
        
        # Đổi sang user không có quyền
        # Cách này không hoạt động trực tiếp trong HttpCase vì session là của admin
        # Thay vào đó, chúng ta có thể mock `request.env.user` trong controller khi test
        # Hoặc gọi endpoint với user khác nếu có cơ chế login cho HttpCase user cụ thể
        
        # Cách tiếp cận: mock has_group để trả về False
        with patch('odoo.addons.digi_moodle_sync.controllers.users_sync.request') as mock_request:
            mock_request.env.user = self.test_user_no_rights
            # Giả lập thêm các thuộc tính cần thiết cho mock_request nếu controller sử dụng
            mock_request.env.company = self.env.company
            mock_request.env.cr = self.env.cr
            mock_request.env.context = self.env.context
            mock_request.httprequest.headers = {}
            mock_request.httprequest.remote_addr = '127.0.0.1'

            # Gọi controller method trực tiếp (khó hơn vì nó là HTTP controller)
            # Hoặc dùng self.url_open để gọi endpoint
            response = self.url_open('/moodle/sync_users') # Sẽ chạy với user của session HttpCase (admin)
            # Do đó, để test quyền, ta cần mock sâu hơn hoặc gọi phương thức check_access_rights riêng

            # Test _check_access_rights trực tiếp
            from odoo.addons.digi_moodle_sync.controllers.users_sync import MoodleUserSyncController
            controller = MoodleUserSyncController()
            
            # Mock request.env.user cho lần gọi _check_access_rights
            original_user = self.env.user
            try:
                self.env.user = self.test_user_no_rights
                # Cần patch request được sử dụng bên trong controller
                with patch('odoo.addons.digi_moodle_sync.controllers.users_sync.request.env.user', self.test_user_no_rights):
                    with self.assertRaises(AccessError):
                        controller._check_access_rights() # Gọi hàm kiểm tra quyền
            finally:
                self.env.user = original_user # Khôi phục user

    def test_sync_users_success_with_rights(self):
        """Test sync_users endpoint success for user with rights (mocking API call)."""
        if not self.moodle_sync_manager_group:
            self.skipTest("Moodle Sync Manager group not found, skipping permission test.")

        # Đăng nhập với user có quyền (HttpCase mặc định là admin, đã có mọi quyền)
        # Nếu muốn test với self.user_with_rights, cần authenticate_user(self.user_with_rights.login, 'password_cua_user_do')
        # Hoặc mock has_group để trả về True

        mock_api_response = {
            'users': [
                {
                    'id': 101, 'username': 'muser1', 'fullname': 'Moodle User One',
                    'email': 'muser1@example.com', 'firstaccess': 1670000000,
                    'lastaccess': 1670000000, 'auth': 'manual', 'suspended': False,
                    'confirmed': True, 'lang': 'en', 'theme': 'boost',
                    'timezone': 'UTC', 'country': 'US'
                },
                {
                    'id': 102, 'username': 'muser2', 'fullname': 'Moodle User Two',
                    'email': 'muser2@example.com'
                }
            ]
        }

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response
            mock_get.return_value = mock_response
            
            # Đảm bảo user đang chạy là user có quyền
            # Mặc định HttpCase chạy với admin

            response = self.url_open('/moodle/sync_users')
            self.assertEqual(response.status_code, 200)
            json_response = response.json()
            self.assertIn('message', json_response)
            self.assertIn('created_odoo_users', json_response)
            self.assertIn('updated_odoo_users', json_response)
            self.assertEqual(json_response['created_odoo_users'], 2) # Giả sử đây là lần đầu, tạo 2 users

            # Kiểm tra xem user đã được tạo/cập nhật trong Odoo chưa
            user1_odoo = self.env['res.users'].search([('moodle_id', '=', 101)])
            self.assertTrue(user1_odoo)
            self.assertEqual(user1_odoo.name, 'Moodle User One')
            self.assertEqual(user1_odoo.email, 'muser1@example.com')
            self.assertIsNotNone(user1_odoo.partner_id)
            self.assertEqual(user1_odoo.partner_id.email, 'muser1@example.com')

            user2_odoo = self.env['res.users'].search([('moodle_id', '=', 102)])
            self.assertTrue(user2_odoo)
            self.assertEqual(user2_odoo.name, 'Moodle User Two')

            # Kiểm tra moodle.user
            moodle_user1 = self.env['moodle.user'].search([('moodle_id', '=', 101)])
            self.assertTrue(moodle_user1)
            self.assertEqual(moodle_user1.name, 'Moodle User One')
            self.assertEqual(moodle_user1.odoo_user_id, user1_odoo)
            self.assertIsNotNone(moodle_user1.last_sync_date)

    def test_sync_users_update_existing(self):
        """Test updating existing Odoo users and moodle.user records."""
        # Tạo user Odoo và moodle.user giả lập đã tồn tại
        existing_odoo_user = self.env['res.users'].create({
            'name': 'Old Name',
            'login': 'existing@example.com',
            'email': 'existing@example.com',
            'moodle_id': 201 # Moodle ID đã có
        })
        existing_moodle_app_user = self.env['moodle.user'].create({
            'name': 'Old Moodle Name',
            'moodle_id': 201,
            'odoo_user_id': existing_odoo_user.id,
            'email': 'existing@example.com'
        })

        mock_api_response = {
            'users': [
                {
                    'id': 201, 'username': 'muser_updated', 'fullname': 'Moodle User Updated',
                    'email': 'updated_email@example.com' # Email cũng thay đổi
                }
            ]
        }

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response
            mock_get.return_value = mock_response

            response = self.url_open('/moodle/sync_users')
            self.assertEqual(response.status_code, 200)
            json_response = response.json()
            self.assertEqual(json_response['created_odoo_users'], 0)
            self.assertEqual(json_response['updated_odoo_users'], 1)
            self.assertEqual(json_response['updated_moodle_users'], 1)

            existing_odoo_user.invalidate_cache()
            existing_moodle_app_user.invalidate_cache()
            self.assertEqual(existing_odoo_user.name, 'Moodle User Updated')
            self.assertEqual(existing_odoo_user.email, 'updated_email@example.com')
            self.assertEqual(existing_odoo_user.login, 'updated_email@example.com') # Kiểm tra login được cập nhật

            self.assertEqual(existing_moodle_app_user.name, 'Moodle User Updated')
            self.assertEqual(existing_moodle_app_user.email, 'updated_email@example.com')
            self.assertIsNotNone(existing_moodle_app_user.last_sync_date)

    def test_sync_users_api_error(self):
        """Test handling of Moodle API error."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500 # Lỗi server từ Moodle
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Fake HTTP Error")
            mock_get.return_value = mock_response

            response = self.url_open('/moodle/sync_users')
            self.assertEqual(response.status_code, 502) # Hoặc mã lỗi tương ứng bạn đặt
            json_response = response.json()
            self.assertIn('error', json_response)
            self.assertTrue("Moodle API trả về status 500" in json_response['error'] or "Lỗi kết nối Moodle API" in json_response['error'])

    def test_sync_users_missing_config(self):
        """Test handling of missing Moodle configuration."""
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.token', False)
        response = self.url_open('/moodle/sync_users')
        self.assertEqual(response.status_code, 503) # Hoặc mã lỗi bạn đặt cho config thiếu
        json_response = response.json()
        self.assertIn('error', json_response)
        self.assertIn("Moodle URL/Token chưa cấu hình" in json_response['error'] or "Moodle configuration is missing" in json_response['error'])

    # Thêm các test case khác: 
    # - User từ Moodle đã tồn tại trong Odoo qua email nhưng chưa có moodle_id -> moodle_id được link
    # - Dữ liệu API rỗng
    # - Dữ liệu API có user thiếu thông tin quan trọng (id, email)
    # - Xung đột email (ví dụ: moodle user có email X, nhưng user Odoo Y đã dùng email X và có moodle_id khác)

if __name__ == '__main__':
    unittest.main() 