from odoo import models, fields, api

class MoodleAssignmentSubmission(models.Model):
    _name = 'moodle.assignment.submission'
    _description = 'Moodle Assignment Submission'

    assignment_id = fields.Many2one('moodle.assignment', string='Assignment', required=True)
    user_id = fields.Many2one('res.users', string='Student', required=True)
    status = fields.Selection([
        ('new', 'New'),
        ('submitted', 'Submitted'),
        ('draft', 'Draft'),
        ('graded', 'Graded')
    ], string='Status', required=True)
    timemodified = fields.Datetime(string='Last Modified')
    grade = fields.Float(string='Grade')

    _sql_constraints = [
        ('unique_submission', 
         'UNIQUE(assignment_id, user_id)',
         'Only one submission per student per assignment is allowed!')
    ] 