# Digi Moodle Sync

Module đồng bộ dữ liệu giữa Odoo 15 và Moodle LMS thông qua REST API.

## 🌟 Tính năng

### 1. Đồng bộ tiến độ học tập
- Lấy trạng thái hoàn thành các hoạt động trong khóa học
- Theo dõi tiến độ của từng học viên
- API sử dụng: `core_completion_get_activities_completion_status`

### 2. Đồng bộ bài tập
- Lấy danh sách bài tập từ các khóa học
- Thông tin bài tập: tên, ngày hết hạn, khóa học
- API sử dụng: `mod_assign_get_assignments`

### 3. Đồng bộ bài nộp
- Lấy danh sách bài nộp của học viên
- Thông tin bài nộp: trạng thái, điểm số, ngày nộp
- API sử dụng: `mod_assign_get_submissions`

### 4. Đồng bộ giáo viên
- Lấy danh sách giáo viên của từng khóa học
- Thông tin giáo viên: họ tên, email
- API sử dụng: `core_enrol_get_enrolled_users`

## 🛠 Cài đặt

1. Cài đặt module:
```bash
# Copy module vào thư mục addons
cp -r digi_moodle_sync /path/to/odoo/addons/

# Cập nhật danh sách module
./odoo-bin -d your_database -u digi_moodle_sync
```

2. Cấu hình kết nối Moodle:
- Vào **Settings > Technical > Parameters > System Parameters**
- Thêm các thông số:
  - `moodle.wstoken`: Token xác thực Moodle Web Service
  - `moodle.url`: URL của server Moodle

## 📝 Hướng dẫn sử dụng

### Đồng bộ dữ liệu
1. Vào menu **Moodle Sync**
2. Click nút **Sync with Moodle**
3. Chọn loại dữ liệu cần đồng bộ:
   - Activity Progress: Tiến độ hoạt động
   - Assignments: Bài tập
   - Assignment Submissions: Bài nộp
   - Course Teachers: Giáo viên
   - All Data: Tất cả dữ liệu
4. Click **Sync** để bắt đầu đồng bộ

### Xem dữ liệu
- **Activity Progress**: Xem tiến độ hoạt động của học viên
- **Assignments**: Xem danh sách bài tập
- **Assignment Submissions**: Xem bài nộp và điểm số
- **Course Teachers**: Xem danh sách giáo viên theo khóa học

## 🔧 Yêu cầu kỹ thuật

- Odoo 15.0
- Python 3.7+
- Moodle 3.9+ với Web Services được kích hoạt
- Các API Moodle cần được bật:
  - core_completion_get_activities_completion_status
  - mod_assign_get_assignments
  - mod_assign_get_submissions
  - core_enrol_get_enrolled_users

## 🔒 Bảo mật

- Token Moodle cần có quyền truy cập các API được sử dụng
- Chỉ admin có quyền cấu hình kết nối
- Dữ liệu được đồng bộ theo phân quyền của người dùng

## 🐛 Xử lý lỗi

- Kiểm tra log trong Odoo để xem chi tiết lỗi
- Đảm bảo token Moodle còn hiệu lực
- Kiểm tra kết nối internet
- Xác nhận URL Moodle chính xác và có thể truy cập

## 📞 Hỗ trợ

- Website: https://digitalwave.vn
- Email: support@digitalwave.vn
- Điện thoại: xxx-xxx-xxxx

## 📄 License

LGPL-3 