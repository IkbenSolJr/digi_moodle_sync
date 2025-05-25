# -*- coding: utf-8 -*-
from odoo import models, fields

class MoodleUserCourse(models.Model):
    _name = 'moodle.user.course'
    _description = 'Moodle User Course'
    _rec_name = 'course_name'

    moodle_course_id  = fields.Integer(
        "Moodle Course ID", required=True, index=True)
    moodle_user_id    = fields.Many2one(
        'moodle.user', "Moodle User", required=True, ondelete='cascade', index=True)
    course_name       = fields.Char("Course Name", required=True)
    course_shortname  = fields.Char("Course Short Name", required=True)
    enrol_date        = fields.Datetime("Enrollment Date")
    completion_state  = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed')
    ], string="Completion Status", default='not_started', required=True)
    progress_percent  = fields.Float("Progress", default=0.0)
    last_sync_date   = fields.Datetime("Last Synced")

    _sql_constraints = [
        ('unique_moodle_course_user',
         'unique(moodle_course_id,moodle_user_id)',
         'Khóa học này đã được gán cho người dùng Moodle này rồi!')
    ]
