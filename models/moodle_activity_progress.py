from odoo import models, fields, api

class MoodleActivityProgress(models.Model):
    _name = 'moodle.activity.progress'
    _description = 'Moodle Activity Progress'
    _rec_name = 'activity_name'

    userid = fields.Many2one('res.users', string='User', required=True)
    courseid = fields.Many2one('moodle.course', string='Course', required=True)
    cmid = fields.Integer(string='Course Module ID', required=True)
    activity_name = fields.Char(string='Activity Name')
    completionstate = fields.Selection([
        ('0', 'Not Completed'),
        ('1', 'Completed'),
        ('2', 'Completed with Pass'),
        ('3', 'Completed with Fail')
    ], string='Completion State', required=True)
    timemodified = fields.Datetime(string='Last Modified')

    _sql_constraints = [
        ('unique_activity_user', 
         'UNIQUE(userid, courseid, cmid)',
         'Activity progress must be unique per user and activity!')
    ] 