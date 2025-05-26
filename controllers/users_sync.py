# -*- coding: utf-8 -*-
import logging
import requests
import json
from datetime import datetime

from odoo import http
from odoo.http import request
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)

MOODLE_SYNC_MANAGER_GROUP = 'digi_moodle_sync.group_manager'

class MoodleUserSyncController(http.Controller):

    def _check_access_rights(self):
        if not request.env.user.has_group(MOODLE_SYNC_MANAGER_GROUP):
            _logger.warning(
                f"User {request.env.user.login} (ID: {request.env.user.id}) attempt to access Moodle User Sync without proper rights."
            )
            raise AccessError("Bạn không có quyền thực hiện hành động này. Vui lòng liên hệ quản trị viên.")

    @http.route('/moodle/sync_users', type='http', auth='user', methods=['GET'], csrf=False)
    def sync_users(self, **kw):
        # Audit Log and Access Check
        _logger.info(
            f"User Sync: User {request.env.user.login} (ID: {request.env.user.id}) initiated user sync. Params: {kw}"
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
            _logger.error("Moodle URL hoặc Token chưa được cấu hình.")
            return request.make_response(
                json.dumps({'error': 'Moodle URL/Token chưa cấu hình.'}), 
                headers=[('Content-Type', 'application/json')])

        api_url = base_moodle_url.rstrip('/') + '/webservice/rest/server.php'
        params = {
            'wstoken': token,
            'wsfunction': 'core_user_get_users',
            'criteria[0][key]': 'email',
            'criteria[0][value]': '%',
            'moodlewsrestformat': 'json'
        }

        try:
            _logger.info("Bắt đầu đồng bộ người dùng từ Moodle API: %s", api_url)
            resp = requests.get(api_url, params=params, timeout=60) 

            if resp.status_code != 200:
                _logger.error(
                    "Lỗi API Moodle (core_user_get_users): Status %s, Phản hồi: %s",
                    resp.status_code, resp.text[:500])
                return request.make_response(
                    json.dumps({'error': f'Moodle API trả về status {resp.status_code}'}),
                    headers=[('Content-Type', 'application/json')])
            
            data = resp.json()
            if 'users' not in data or not isinstance(data['users'], list):
                _logger.error("Phản hồi không hợp lệ: thiếu 'users' hoặc sai định dạng. Phản hồi: %s", data)
                return request.make_response(
                    json.dumps({'error': "Không có trường 'users' hợp lệ trong phản hồi từ Moodle."}),
                    headers=[('Content-Type', 'application/json')])

            moodle_users_api_data = data['users']
            _logger.info(f"API Moodle trả về {len(moodle_users_api_data)} người dùng.")
            if not moodle_users_api_data:
                 return request.make_response(json.dumps({'message': 'Không có người dùng nào từ Moodle để đồng bộ.', 'created_odoo_users': 0, 'updated_odoo_users': 0, 'created_moodle_users': 0, 'updated_moodle_users': 0}), headers=[('Content-Type', 'application/json')])

            ResUsers = request.env['res.users'].sudo()
            MoodleAppUser = request.env['moodle.user'].sudo()
            ResPartner = request.env['res.partner'].sudo()

            # Prepare maps for existing records
            all_moodle_ids_from_api = [u['id'] for u in moodle_users_api_data if u.get('id')]
            all_emails_from_api = [u['email'].lower() for u in moodle_users_api_data if u.get('email')]

            existing_odoo_users_by_moodle_id = {u.moodle_id: u for u in ResUsers.search([('moodle_id', 'in', all_moodle_ids_from_api)])}
            existing_odoo_users_by_email = {u.email.lower(): u for u in ResUsers.search([('email', 'ilike', '%')]) if u.email} # Fetch all for broader email check
            
            existing_moodle_app_users_by_moodle_id = {mu.moodle_id: mu for mu in MoodleAppUser.search([('moodle_id', 'in', all_moodle_ids_from_api)])}
            
            odoo_users_to_create_vals = []
            odoo_users_to_update_map = {} # {odoo_user_id: vals}
            moodle_app_users_to_create_vals = []
            moodle_app_users_to_update_map = {} # {moodle_app_user_id: vals}

            processed_moodle_ids = set()

            for u_api in moodle_users_api_data:
                moodle_id = u_api.get('id')
                email = u_api.get('email', '').lower().strip()
                username = u_api.get('username', '')
                fullname = u_api.get('fullname', username or email or f"Moodle User {moodle_id}")

                if not moodle_id or not email:
                    _logger.warning(f"Bỏ qua user từ Moodle do thiếu Moodle ID ({moodle_id}) hoặc Email ({email}). Data: {u_api}")
                    continue
                
                if moodle_id in processed_moodle_ids:
                    _logger.debug(f"Moodle ID {moodle_id} đã được xử lý, bỏ qua trùng lặp từ API.")
                    continue
                processed_moodle_ids.add(moodle_id)

                odoo_user = None
                # 1. Find Odoo User by Moodle ID first
                if moodle_id in existing_odoo_users_by_moodle_id:
                    odoo_user = existing_odoo_users_by_moodle_id[moodle_id]
                # 2. If not found, find by email
                elif email in existing_odoo_users_by_email:
                    odoo_user = existing_odoo_users_by_email[email]
                    # Link Moodle ID if found by email and not yet linked
                    if odoo_user and not odoo_user.moodle_id:
                        odoo_users_to_update_map.setdefault(odoo_user.id, {}).update({'moodle_id': moodle_id})
                
                # Prepare Odoo User vals
                odoo_user_update_vals = {
                    'name': fullname,
                    'login': odoo_user.login if odoo_user and odoo_user.login else email, # Keep existing login if user exists
                    'email': email,
                    'moodle_id': moodle_id # Ensure Moodle ID is set/updated
                }

                if odoo_user:
                    # Check for changes before adding to update map
                    current_vals = {k: odoo_user[k] for k in odoo_user_update_vals.keys() if k in odoo_user}
                    if any(odoo_user_update_vals[k] != current_vals.get(k) for k in odoo_user_update_vals):
                        odoo_users_to_update_map.setdefault(odoo_user.id, {}).update(odoo_user_update_vals)
                else:
                    # Create new Partner first for the new Odoo User
                    partner_vals = {
                        'name': fullname,
                        'email': email,
                        'company_id': request.env.company.id, # Ensure company context
                    }
                    # We will create partner along with user to ensure atomicity if possible or handle failure
                    odoo_user_create_val = dict(odoo_user_update_vals)
                    odoo_user_create_val['partner_vals_for_creation'] = partner_vals # Temp store for batch creation
                    odoo_users_to_create_vals.append(odoo_user_create_val)

                # Prepare Moodle App User (moodle.user) vals
                moodle_app_user_vals = {
                    'name': fullname,
                    'login': username or email, # Moodle username might be different from email
                    'email': email,
                    'moodle_id': moodle_id,
                    'odoo_user_id': odoo_user.id if odoo_user else None, # Link later if Odoo user is created
                    'last_sync_date': datetime.now(),
                }
                if moodle_id in existing_moodle_app_users_by_moodle_id:
                    mu_record = existing_moodle_app_users_by_moodle_id[moodle_id]
                    current_mu_vals = {k: mu_record[k] for k in moodle_app_user_vals.keys() if k in mu_record}
                    if any(moodle_app_user_vals[k] != current_mu_vals.get(k) for k in moodle_app_user_vals):
                        moodle_app_users_to_update_map.setdefault(mu_record.id, {}).update(moodle_app_user_vals)
                else:
                    moodle_app_users_to_create_vals.append(moodle_app_user_vals)

            # Batch Create Odoo Users (res.users)
            created_odoo_users_count = 0
            newly_created_odoo_users_map_by_moodle_id = {}
            if odoo_users_to_create_vals:
                final_odoo_user_create_list = []
                for user_val_with_partner in odoo_users_to_create_vals:
                    partner_vals = user_val_with_partner.pop('partner_vals_for_creation')
                    try:
                        partner = ResPartner.create(partner_vals)
                        user_val_with_partner['partner_id'] = partner.id
                        user_val_with_partner['company_id'] = partner.company_id.id or request.env.company.id
                        user_val_with_partner['company_ids'] = [(6, 0, [partner.company_id.id or request.env.company.id])]
                        final_odoo_user_create_list.append(user_val_with_partner)
                    except Exception as e_partner:
                        _logger.error(f"Không thể tạo Partner cho Odoo User (email: {user_val_with_partner.get('email')}). Lỗi: {e_partner}")
                
                if final_odoo_user_create_list:
                    try:
                        created_odoo_users = ResUsers.with_context(no_reset_password=True).create(final_odoo_user_create_list)
                        created_odoo_users_count = len(created_odoo_users)
                        for nou in created_odoo_users: newly_created_odoo_users_map_by_moodle_id[nou.moodle_id] = nou
                        _logger.debug(f"Batch created {created_odoo_users_count} res.users.")
                    except Exception as e_create_batch_ou:
                        _logger.error(f"Lỗi batch create res.users: {e_create_batch_ou}", exc_info=True)
                        # Fallback could be implemented here if critical
            
            # Update Odoo User references in Moodle App User creation list
            for mu_create_val in moodle_app_users_to_create_vals:
                if not mu_create_val.get('odoo_user_id') and mu_create_val.get('moodle_id') in newly_created_odoo_users_map_by_moodle_id:
                    mu_create_val['odoo_user_id'] = newly_created_odoo_users_map_by_moodle_id[mu_create_val['moodle_id']].id
            
            # Batch Create Moodle App Users (moodle.user)
            created_moodle_users_count = 0
            if moodle_app_users_to_create_vals:
                try:
                    MoodleAppUser.create(moodle_app_users_to_create_vals)
                    created_moodle_users_count = len(moodle_app_users_to_create_vals)
                    _logger.debug(f"Batch created {created_moodle_users_count} moodle.user records.")
                except Exception as e_create_batch_mu:
                    _logger.error(f"Lỗi batch create moodle.user: {e_create_batch_mu}", exc_info=True)

            # Batch Update Odoo Users
            updated_odoo_users_count = 0
            for user_id, vals_u_update in odoo_users_to_update_map.items():
                try:
                    ResUsers.browse(user_id).write(vals_u_update)
                    updated_odoo_users_count += 1
                    _logger.debug(f"Updated res.users ID {user_id}.")
                except Exception as e_update_ou:
                    _logger.error(f"Lỗi cập nhật res.users ID {user_id}: {e_update_ou}")
            
            # Update Odoo User references in Moodle App User update list
            for mu_update_vals in moodle_app_users_to_update_map.values():
                 if not mu_update_vals.get('odoo_user_id') and mu_update_vals.get('moodle_id') in newly_created_odoo_users_map_by_moodle_id:
                    mu_update_vals['odoo_user_id'] = newly_created_odoo_users_map_by_moodle_id[mu_update_vals['moodle_id']].id
                 elif not mu_update_vals.get('odoo_user_id') and mu_update_vals.get('moodle_id') in existing_odoo_users_by_moodle_id:
                     mu_update_vals['odoo_user_id'] = existing_odoo_users_by_moodle_id[mu_update_vals['moodle_id']].id

            # Batch Update Moodle App Users
            updated_moodle_users_count = 0
            for mu_id, vals_mu_update in moodle_app_users_to_update_map.items():
                try:
                    MoodleAppUser.browse(mu_id).write(vals_mu_update)
                    updated_moodle_users_count += 1
                    _logger.debug(f"Updated moodle.user ID {mu_id}.")
                except Exception as e_update_mu:
                     _logger.error(f"Lỗi cập nhật moodle.user ID {mu_id}: {e_update_mu}")

            summary_msg = (
                f"Đồng bộ người dùng hoàn tất. "
                f"Odoo Users: {created_odoo_users_count} tạo mới, {updated_odoo_users_count} cập nhật. "
                f"Moodle App Users: {created_moodle_users_count} tạo mới, {updated_moodle_users_count} cập nhật."
            )
            _logger.info(summary_msg)
            config.set_param('digi_moodle_sync.last_users_sync_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            return request.make_response(
                json.dumps({
                    'message': summary_msg, 
                    'created_odoo_users': created_odoo_users_count, 'updated_odoo_users': updated_odoo_users_count,
                    'created_moodle_users': created_moodle_users_count, 'updated_moodle_users': updated_moodle_users_count
                }),
                headers=[('Content-Type', 'application/json')])

        except requests.exceptions.Timeout as e_timeout:
            _logger.error("Timeout khi gọi Moodle API (core_user_get_users): %s", e_timeout)
            return request.make_response(json.dumps({'error': 'Timeout khi kết nối Moodle API.'}), status=504, headers=[('Content-Type', 'application/json')])
        except requests.exceptions.RequestException as e_req:
            _logger.error("Lỗi RequestException khi gọi Moodle API (core_user_get_users): %s", e_req)
            return request.make_response(json.dumps({'error': f'Lỗi kết nối Moodle API: {e_req}'}), status=502, headers=[('Content-Type', 'application/json')])
        except Exception as e_main:
            _logger.error("Lỗi không xác định trong quá trình đồng bộ người dùng: %s", e_main, exc_info=True)
            return request.make_response(json.dumps({'error': f'Lỗi không xác định: {e_main}'}), status=500, headers=[('Content-Type', 'application/json')])

# Make sure __init__.py imports this controller
# from . import users_sync
