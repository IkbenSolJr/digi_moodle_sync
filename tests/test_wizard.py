# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import AccessError

@tagged('-at_install', 'post_install')
class TestMoodleSyncWizard(TransactionCase):
    def setUp(self):
        super(TestMoodleSyncWizard, self).setUp()
        self.env = self.env(user=self.env.ref('base.user_admin')) # Chạy test với admin

        self.moodle_sync_manager_group = self.env.ref('digi_moodle_sync.group_manager', raise_if_not_found=False)
        self.test_user_no_rights = self.env['res.users'].create({
            'name': 'Wizard Test User No Rights',
            'login': 'wizard_test_no_rights',
        })
        self.user_with_rights = self.env['res.users'].create({
            'name': 'Wizard Test User With Rights',
            'login': 'wizard_test_with_rights',
            'groups_id': [(6, 0, [self.moodle_sync_manager_group.id])] if self.moodle_sync_manager_group else []
        })

        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.moodle_url', 'https://fakemoodle.example.com')
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.token', 'faketoken123')

    def test_wizard_access_denied(self):
        """Test wizard access denied for user without rights."""
        if not self.moodle_sync_manager_group:
            self.skipTest("Moodle Sync Manager group not found.")

        wizard = self.env['moodle.sync.wizard'].with_user(self.test_user_no_rights).create({
            'sync_type': 'all'
        })
        with self.assertRaises(AccessError):
            wizard.action_sync() # Sẽ raise AccessError từ _check_access_rights_for_wizard

    @patch('odoo.addons.digi_moodle_sync.wizard.moodle_sync_wizard.MoodleSyncWizard._sync_users')
    @patch('odoo.addons.digi_moodle_sync.wizard.moodle_sync_wizard.MoodleSyncWizard._sync_activities')
    @patch('odoo.addons.digi_moodle_sync.wizard.moodle_sync_wizard.MoodleSyncWizard._sync_assignments')
    @patch('odoo.addons.digi_moodle_sync.wizard.moodle_sync_wizard.MoodleSyncWizard._sync_submissions')
    @patch('odoo.addons.digi_moodle_sync.controllers.teacher_sync.MoodleTeacherSync.sync_teachers') # Patch method của controller
    def test_wizard_sync_all_success(self, mock_sync_teachers, mock_sync_submissions, mock_sync_assignments, mock_sync_activities, mock_sync_users):
        """Test wizard action_sync with type 'all' success (mocking sync methods)."""
        if not self.moodle_sync_manager_group:
            self.skipTest("Moodle Sync Manager group not found, test might not reflect true permission pass.")

        # Giả lập các hàm sync con được gọi thành công
        mock_sync_users.return_value = None
        mock_sync_activities.return_value = None
        mock_sync_assignments.return_value = None
        mock_sync_submissions.return_value = None
        mock_sync_teachers.return_value = "Teachers synced successfully via wizard mock."

        wizard = self.env['moodle.sync.wizard'].with_user(self.user_with_rights).create({
            'sync_type': 'all'
        })
        result_action = wizard.action_sync()

        self.assertIsNotNone(result_action)
        self.assertEqual(result_action.get('type'), 'ir.actions.client')
        self.assertEqual(result_action.get('tag'), 'display_notification')
        self.assertEqual(result_action.get('params', {}).get('type'), 'success')

        mock_sync_users.assert_called_once()
        mock_sync_activities.assert_called_once()
        mock_sync_assignments.assert_called_once()
        mock_sync_submissions.assert_called_once()
        mock_sync_teachers.assert_called_once()
        
    @patch('odoo.addons.digi_moodle_sync.wizard.moodle_sync_wizard.MoodleSyncWizard._sync_activities')
    def test_wizard_sync_activity_only(self, mock_sync_activities):
        """Test wizard action_sync with type 'activity'."""
        if not self.moodle_sync_manager_group:
            self.skipTest("Moodle Sync Manager group not found.")

        mock_sync_activities.return_value = None
        
        wizard = self.env['moodle.sync.wizard'].with_user(self.user_with_rights).create({
            'sync_type': 'activity'
        })
        wizard.action_sync()
        mock_sync_activities.assert_called_once()
        # Cũng cần mock _sync_users vì nó luôn được gọi trước

    # Thêm test cho các trường hợp lỗi cấu hình (thiếu token/url)
    def test_wizard_missing_config(self):
        """Test wizard when Moodle config is missing."""
        self.env['ir.config_parameter'].sudo().set_param('digi_moodle_sync.token', False)
        wizard = self.env['moodle.sync.wizard'].with_user(self.user_with_rights).create({
            'sync_type': 'all'
        })
        result_action = wizard.action_sync()
        self.assertEqual(result_action.get('params', {}).get('type'), 'danger')
        self.assertIn('Moodle configuration is missing', result_action.get('params', {}).get('message', ''))

# Các test case khác:
# - Test từng sync_type cụ thể (assignment, submission, teacher) xem các mock tương ứng có được gọi không.
# - Test trường hợp các hàm sync con raise Exception.

if __name__ == '__main__':
    unittest.main() 