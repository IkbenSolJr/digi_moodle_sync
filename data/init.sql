-- Thêm cột moodle_id vào bảng res_users
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'res_users' 
        AND column_name = 'moodle_id'
    ) THEN
        ALTER TABLE res_users ADD COLUMN moodle_id integer;
    END IF;
END $$; 