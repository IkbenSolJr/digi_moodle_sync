# Digi Moodle Sync

> **Module đồng bộ dữ liệu Moodle với Odoo 15.0**

## Tổng quan

Module này kết nối Odoo với hệ thống học trực tuyến Moodle, đồng bộ thông tin người dùng, khóa học, điểm số và bài tập.

## Các tính năng

- Đồng bộ người dùng (học viên, giảng viên) từ Moodle sang Odoo
- Đồng bộ thông tin khóa học
- Đồng bộ kết quả học tập và điểm số
- Đồng bộ thông tin bài tập và bài nộp

## Cấu hình

1. Cài đặt module
2. Truy cập **Moodle Sync > Cấu hình**
3. Nhập các thông số:
   - Moodle URL: Địa chỉ URL gốc của trang Moodle (VD: https://moodle.example.com)
   - Moodle Token: Token webservice để truy cập API
4. Lưu cấu hình và kiểm tra kết nối

## Các thay đổi quan trọng đã cập nhật:

1. **Thống nhất URL Moodle**
   - Cập nhật để chỉ lưu URL gốc (domain hoặc thư mục gốc) trong trường `moodle_url`
   - Tất cả API call đều tự động thêm `/webservice/rest/server.php` vào URL trước khi gửi request

2. **Đồng bộ và lưu trữ Moodle ID**
   - Đảm bảo `moodle_id` được lưu vào `res.users` khi nhận kết quả từ API
   - Khi tạo user mới, luôn thêm `moodle_id` vào vals trước khi create()

3. **Sử dụng đúng ID Moodle khi gọi API**
   - Trong các hàm đồng bộ, sử dụng `user.moodle_id` thay vì `user.id` để truyền vào tham số `userid`
   - Đảm bảo có bản ghi `moodle.user` tương ứng trước khi tạo bản ghi con

4. **Đồng bộ mô hình dữ liệu**
   - Đảm bảo quan hệ Many2one chỉ đến mô hình đúng
   - Đổi tên field `user_id` thành `moodle_user_id` trong các mô hình liên quan

5. **Hiệu chỉnh chức năng Dashboard**
   - Cập nhật các action view để mở đúng view tương ứng
   - Triển khai kiểm thử kết nối
   - Tạo biểu đồ thống kê đơn giản

6. **Nâng cao xử lý ngoại lệ**
   - Thêm logging chi tiết cho từng API call
   - Kiểm tra HTTP status và nội dung trả về
   - Bổ sung try/except để không làm sập cron/job

## Hướng dẫn sử dụng

### Đồng bộ thông tin

1. **Đồng bộ người dùng**: `/moodle/sync_users`
2. **Đồng bộ khóa học**: `/moodle/sync_courses`
3. **Đồng bộ điểm số**: `/moodle/sync_courses_grades?userid=X`
4. **Đồng bộ giảng viên**: `/moodle/sync/teachers`
5. **Đồng bộ bài tập**: `/moodle/sync/assignments`

### Xem dữ liệu

Truy cập từ menu **Moodle Sync > Dashboard** để xem tổng quan và truy cập các dữ liệu đã đồng bộ.

## Lưu ý

- Cần có quyền admin trên Moodle để tạo token với đầy đủ quyền truy cập API
- Chức năng đồng bộ nên được lên lịch chạy định kỳ để dữ liệu luôn cập nhật
- Kiểm tra log khi có lỗi (từ menu **Cài đặt > Kỹ thuật > Logs**)

---

© 2023 Digital Service Solution Education (DSSE) 