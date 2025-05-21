# -*- coding: utf-8 -*-
import logging
import requests
import json

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class MoodleUserSyncController(http.Controller):

    @http.route('/moodle/sync_users', type='http', auth='public', methods=['GET'], csrf=False)
    def sync_users(self, **kw):
        config     = request.env['ir.config_parameter'].sudo()
        moodle_url = config.get_param('digi_moodle_sync.moodle_url')
        token      = config.get_param('digi_moodle_sync.token')

        params = {
            'wstoken':            token,
            'wsfunction':         'core_user_get_users',
            'moodlewsrestformat': 'json',
            'criteria[0][key]':   'email',
            'criteria[0][value]': '%'
        }
        try:
            resp = requests.get(moodle_url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if 'users' not in data:
                _logger.error("Invalid response from Moodle: missing 'users'")
                return request.make_response(
                    json.dumps({'error': 'Không có trường users trong response'}),
                    headers=[('Content-Type','application/json')])

            User = request.env['res.users'].sudo()
            existing = {u.email for u in User.search([]) if u.email}
            created = updated = 0

            for u in data['users']:
                email = (u.get('email') or '').strip()
                if not email:
                    continue

                vals = {
                    'name':  u.get('fullname'),
                    'login': u.get('username'),
                }
                if email in existing:
                    user = User.search([('email','=', email)], limit=1)
                    if user:
                        user.write(vals)
                        updated += 1
                else:
                    vals.update({
                        'email':      email,
                        'company_id': request.env.user.company_id.id,
                    })
                    User.create(vals)
                    created += 1

            _logger.info("Users sync: %d created, %d updated", created, updated)
            return request.make_response(
                json.dumps({'message':'Users synchronized','created':created,'updated':updated}),
                headers=[('Content-Type','application/json')])
        except requests.RequestException as e:
            _logger.error("Connection error: %s", e)
            return request.make_response(
                json.dumps({'error': f'Không thể kết nối Moodle: {e}'}),
                headers=[('Content-Type','application/json')])
        except Exception as e:
            _logger.error("Unexpected error: %s", e)
            return request.make_response(
                json.dumps({'error': f'Lỗi không xác định: {e}'}),
                headers=[('Content-Type','application/json')])
