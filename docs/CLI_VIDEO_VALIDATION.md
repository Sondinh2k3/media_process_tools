# CLI cắt video và kiểm chứng trên dữ liệu thực tế

Ngày thực hiện: **05/11/2026**, Windows 11, Python 3.12.10, PySide6 6.10.3. Người dùng đã yêu cầu trực tiếp thử video trong thư mục `video`.

## Cách dùng một lệnh

```powershell
.\.venv\Scripts\python.exe -m video_dataset_tool cut --input ".\video\Video_000.mp4" --start 10.250 --end 20.750 --output-dir ".\exports\Video_000"
```

- Mặc định `precise` → H.264/AAC trong MP4. `--mode fast` → stream copy sang MKV.
- Chấp nhận giây thập phân hoặc `HH:MM:SS[.mmm]`, đến mili giây. Có thể thay `--end` bằng `--duration`.
- CLI ghi thẳng vào `--output-dir`, tạo thư mục nếu chưa có. ID nguồn đầy đủ, hoa/thường và khoảng cắt đều có trong tên clip; UUID tránh ghi đè khi chạy lại.
- `--json` in kết quả có `video_id` (ID từ tên nguồn), `source_video_id` (UUID SQLite), đường dẫn clip, khoảng yêu cầu, thời lượng đo và trạng thái. Tiến độ dùng stderr.
- `--data-dir` chọn SQLite/log; mặc định dùng dataset OS chung GUI. Lần thử này dùng `--data-dir ".\exports\.dataset"` để giữ metadata kiểm chứng riêng trong workspace.
- Ctrl+C hủy có kiểm soát. Mã thoát: 0 thành công, 1 lỗi xử lý, 2 lỗi cú pháp, 130 đã hủy. GUI/lệnh khác đang giữ cùng dataset sẽ được báo rõ, không sửa trạng thái job của phiên kia.

## Nguồn và quy tắc đặt tên

Nguồn `video/Video_000.mp4`: **149.538.609 byte**, **114.455 ms**, **1920×1080**, HEVC và AAC. Không sửa/đổi tên/di chuyển video gốc.

Tên mới có dạng:

```text
Video_000__00-00-10.250_00-00-20.750__<UUID>.mp4
Video_000__00-00-10.250_00-00-20.750__<UUID>.mkv
```

ID nguồn không bị lower-case do canonical path trên Windows, không bị rút gọn 36 ký tự như trước. GUI dùng cùng quy tắc cho các clip xuất mới. Clip đã xuất trước cập nhật vẫn giữ nguyên tên và nội dung.

Tên vượt 255 byte UTF-8 được từ chối với thông báo, không âm thầm cắt ID. Ký tự cấm trên Windows thay bằng `_`. Đường dẫn dài được xử lý bằng extended path khi ghi/probe; có kiểm thử tự động trên tên tiếng Việt dài.

## Kết quả thử video

Khoảng yêu cầu: **10.250–20.750 ms**, độ dài **10.500 ms**.

| Kiểm tra | Precise / MP4 | Fast / MKV |
|---|---|---|
| Trạng thái service và SQLite | completed | completed |
| Thời lượng FFprobe đo | 10.500 ms | 11.370 ms |
| Video / audio | H.264 / AAC | HEVC / AAC |
| Kích thước hình | 1920×1080 | 1920×1080 |
| Kích thước file | 29.858.559 byte | 14.653.118 byte |
| Giải mã toàn bộ video và audio bằng FFmpeg `-xerror` | Không lỗi | Không lỗi |
| Giữ ID `Video_000` trong tên | Đạt | Đạt |

Fast dài hơn khoảng yêu cầu **870 ms** do keyframe/timestamp; vì vậy CLI mặc định Precise. Fast giữ bitstream, còn Precise mã hóa lại nên file có thể lớn hơn nguồn cùng khoảng và mất thời gian hơn. Trong lượt thử này Precise mất khoảng 14,86 giây, Fast khoảng 0,47 giây; đây là số đo một lượt trên máy hiện tại, không phải cam kết hiệu năng.

Frame đầu của clip Precise được so với frame giải mã từ nguồn khi seek 10.250 giây: sai khác RGB tuyệt đối trung bình **1,3044/255**, phù hợp việc mã hóa lại có mất mát. Đây là kiểm tra nội dung bổ sung, không phải bằng chứng bảo đảm frame-accurate cho mọi video.

SHA-256, size, mtime nguồn trước/sau giống nhau. Báo cáo máy đọc và log kiểm tra nằm tại `test-artifacts/real-video-2026-11-05/report.json`; video/clip thực tế không được đưa vào fixture hoặc Git. Hai clip thử nằm trong `exports/Video_000`, SQLite tại `exports/.dataset`.

## Kiểm thử tự động và tương thích

Đã chạy **90 tests đạt, 0 lỗi, 0 skip** với bộ hiện tại. Bao gồm các test V1 và test mới:

- CLI thực chạy không mở GUI, kể cả khi biến QT_QPA_PLATFORM có giá trị không tồn tại.
- Số giây, timecode, IN/OUT/duration và cú pháp không hợp lệ.
- Precise/Fast; đúng thư mục đích trực tiếp; source ID giữ nguyên hoa/thường và ID dài.
- Xuất lặp không ghi đè; metadata completed/failed/cancelled đúng trong SQLite.
- Dataset lock tương thích GUI, SIGINT được đổi thành hủy có kiểm soát và khôi phục signal handler.
- File nguồn mất, đầu ra sai quyền/định dạng, đường dẫn Windows dài, probe lại clip có tên dài.
- GUI xuất với ID hoa/thường vẫn đúng tên mới; lệnh cũ không có `cut` vẫn khởi động GUI.

Ruff lint/format, compileall, pip check và GUI startup smoke đã đạt. JUnit: `test-artifacts/pytest-cli-final.xml`. Ubuntu chưa chạy kiểm chứng; chưa thử toàn bộ codec/driver/định dạng. Không tự bảo đảm độ chính xác tuyệt đối từng frame.
