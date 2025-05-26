from odoo import models, fields, api

class MoodleAssignment(models.Model):
    _name = 'moodle.assignment'
    _description = 'Moodle Assignment'
    _rec_name = 'name'

    moodle_id = fields.Integer(string='Moodle Assignment ID', required=True, index=True)
    name = fields.Char(string='Assignment Name', required=True)
    duedate = fields.Datetime(string='Due Date')
    course_id = fields.Many2one('moodle.course', string='Course', required=True, index=True)
    submission_ids = fields.One2many('moodle.assignment.submission', 'assignment_id', string='Submissions')
    last_sync_date = fields.Datetime("Last Synced")

    _sql_constraints = [
        ('unique_moodle_assignment', 
         'UNIQUE(moodle_id)',
         'Assignment must be unique per Moodle ID!')
    ] 