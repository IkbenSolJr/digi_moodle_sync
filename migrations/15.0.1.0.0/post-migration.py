def migrate(cr, version):
    # Kiểm tra xem cột moodle_id đã tồn tại chưa
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'res_users' AND column_name = 'moodle_id'")
    if not cr.fetchone():
        # Thêm cột moodle_id
        cr.execute("ALTER TABLE res_users ADD COLUMN moodle_id integer")
        # Cập nhật các giá trị mặc định
        cr.execute("UPDATE res_users SET moodle_id = NULL") 