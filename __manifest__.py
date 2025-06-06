{
    "name": "Digi Moodle Sync",
    # Bản dành cho Odoo 15, theo chuẩn versioning 15.0.x.y.z
    "version": "15.0.1.0.0",
    "category": "Education",
    "summary": "Synchronize data with Moodle LMS",
    "sequence": 1,
    "author": "Sol a.k.a Thien Hoang",
    "website": "https://dsseducation.com",
    "license": "LGPL-3",
    # Thêm web vì module có controller/http
    "depends": [
        "base",
        "web",
        "mail",
    ],
    "data": [
        # 0. SQL init
        "data/init.sql",

        # 1. Security, access, data mẫu
        "security/moodle_sync_security.xml",
        "security/ir.model.access.csv",
        "data/moodle_course_data.xml",

        # 2. Các view & action cơ bản
        "views/moodle_course_views.xml",         # <-- chứa action_moodle_course
        "views/moodle_user_views.xml",
        "views/moodle_user_course_views.xml",
        "views/moodle_user_grade_views.xml",
        "views/res_config_settings_views.xml",
        "views/moodle_sync_wizard_views.xml",
        "views/moodle_dashboard_views.xml",

        # 3. Menu cuối cùng (tham chiếu tất cả action trên)
        "views/moodle_sync_menu.xml",

        # 4. New views
        "views/moodle_sync_views.xml",
    ],
    # Đường dẫn relative, không có dấu "
    "icon": ["static/description/icon.png"],
    "images": ["static/description/banner.png"],
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
