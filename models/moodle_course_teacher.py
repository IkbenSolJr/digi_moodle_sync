from odoo import models, fields, api

class MoodleCourseTeacher(models.Model):
    _name = 'moodle.course.teacher'
    _description = 'Moodle Course Teacher'
    _rec_name = 'fullname'

    user_id = fields.Many2one('res.users', string='User', required=True)
    course_id = fields.Many2one('moodle.course', string='Course', required=True)
    fullname = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email')

    _sql_constraints = [
        ('unique_teacher_course', 
         'UNIQUE(user_id, course_id)',
         'Teacher must be unique per course!')
    ] 