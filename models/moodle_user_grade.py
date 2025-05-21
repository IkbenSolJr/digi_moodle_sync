# -*- coding: utf-8 -*-
from odoo import models, fields

class MoodleUserGrade(models.Model):
    _name = 'moodle.user.grade'
    _description = 'Moodle User Grade'
    _rec_name = 'item_name'

    moodle_user_id    = fields.Many2one(
        'moodle.user', "Moodle User", required=True, ondelete='cascade', index=True)
    moodle_course_id  = fields.Many2one(
        'moodle.user.course', "Moodle Course", required=True, ondelete='cascade', index=True)
    moodle_item_id    = fields.Integer(
        "Moodle Item ID", required=True, index=True)
    item_name         = fields.Char("Item Name", index=True)
    item_type         = fields.Char("Item Type", index=True)
    item_module       = fields.Char("Item Module", index=True)
    grade             = fields.Float("Grade", required=True)
    graded_date       = fields.Datetime("Graded Date")
    is_null_grade     = fields.Boolean("Is Null Grade", default=False,
                                     help="True if the original grade was null")
    last_sync_date    = fields.Datetime("Last Synced")

    _sql_constraints = [
        ('unique_grade_entry',
         'unique(moodle_user_id,moodle_course_id,moodle_item_id)',
         'Bản ghi điểm đã tồn tại!')
    ]
