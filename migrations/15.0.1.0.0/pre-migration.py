def migrate(cr, version):
    # Xóa cột moodle_id nếu tồn tại
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'res_users' AND column_name = 'moodle_id'")
    if cr.fetchone():
        cr.execute("ALTER TABLE res_users DROP COLUMN moodle_id") 