# Kế hoạch và kết quả kiểm thử V1

Ngày kiểm tra: **04/11/2026** (Asia/Saigon).

Cập nhật **05/11/2026**: bổ sung CLI `cut`, quy tắc giữ nguyên ID nguồn, đường dẫn Windows dài và kiểm chứng riêng trên video người dùng cho phép. Sau tối ưu hiệu năng, bộ tự động hiện tại: **101 tests đạt**, không lỗi/skip (22,53 giây ở lượt đầy đủ). Các mốc 60 tests bên dưới là kết quả nghiệm thu V1 ngày 04/11; 90 tests là mốc hoàn tất CLI trước tối ưu. Xem [kiểm chứng CLI](CLI_VIDEO_VALIDATION.md) và [báo cáo hiệu năng](PERFORMANCE.md).

Kiểm tra bổ sung cho đợt tối ưu: migration schema 1→2 giữ clip/ghi chú/preset cũ; phân trang với timestamp trùng không thiếu/trùng clip; COUNT dùng cùng bộ lọc; CSV vẫn đủ mọi trang; debounce chỉ truy vấn một lần sau chuỗi gõ; giữ lựa chọn khi refresh; đăng ký 1.002 đường dẫn theo lô và chống trùng; bỏ ghi draft/setting giống hệt; cache metadata mất hiệu lực khi size/mtime/trạng thái nguồn đổi; Kiểm tra nguồn buộc probe; nút xuất theo nguồn/khoảng hợp lệ; nút hủy chờ worker cleanup; preset được kiểm tra và truyền đúng vào FFmpeg/CLI.

Desktop smoke mới đạt, có frame giải mã, xuất Fast/Precise và CSV, nguồn tổng hợp nguyên hash. Đã xem ảnh bố cục có bộ chọn preset và phân trang tại `test-artifacts/desktop-performance-2026-11-05`. Trên Video_000 thực tế, bốn clip benchmark và một clip CLI mới giải mã hết video/audio không lỗi; nguồn giữ hash/size/mtime. Benchmark và hiện vật nằm trong thư mục Git ignore, không là fixture tự động.

## Môi trường đã chạy

- Windows 11 x64, build 26200.
- Python 3.12.10; PySide6/Qt 6.10.3 (pin trong pyproject); pytest 9.2.0; pytest-qt 4.5.0.
- FFmpeg/FFprobe bản BtbN `N-128352-gec887b13a8-20261103`, lưu cục bộ trong `.tools`; bản này có libx264 và AAC. Nguồn phát hành: [BtbN FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds/releases).
- **Ubuntu chưa được chạy**. Hướng dẫn cài Ubuntu đã viết nhưng không được xem là kết quả thực thi.

Bộ kiểm thử tự động không dùng video của người dùng. Fixture là testsrc2 + sine do FFmpeg sinh, cùng các biến thể không âm thanh, timestamp offset, VFR và màu đơn sắc dài 3.700 giây. Lần kiểm chứng thủ công ngày 05/11 dùng riêng `Video_000.mp4` theo yêu cầu trực tiếp của người dùng, giữ hiện vật cục bộ trong thư mục bị Git ignore.

## Các mốc đã kiểm tra tuần tự

| Mốc | Phần thực hiện | Kết quả khi chuyển mốc |
|---|---|---|
| M1 | Package, ffprobe, player, thư viện, seek, thời gian, lỗi file | 15 tests đạt. |
| M2 | IN/OUT/padding, preview, metadata tình huống, Fast/Precise, progress/cancel, xác minh output | 33 tests đạt. |
| M3 | SQLite migration/transaction, bản nháp/thiết lập, reopen, lịch sử/lọc/CSV, nguồn mất | 37 tests đạt; CLI khởi động/thoát thành công. |
| M4 | Biên/lỗi, VFR, nguồn offset, video dài/tên dài, desktop smoke, kiểm tra layout và tài liệu | Cấu hình cuối chạy hai lượt đầy đủ liên tiếp: 60/60 đạt (19.99s và 20.63s); xem phạm vi và giới hạn bên dưới. |

## Lệnh kiểm chứng

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=test-artifacts\pytest-results.xml
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\ruff.exe format --check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src scripts
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m video_dataset_tool --help
.\.venv\Scripts\python.exe -m video_dataset_tool --data-dir test-artifacts\final-launch --smoke-exit-ms 1500
.\.venv\Scripts\python.exe scripts\smoke_desktop.py --output-dir test-artifacts\desktop-release
```

Các lệnh lint/format/compile/dependency check và GUI launch đã chạy thành công. `--smoke-exit-ms` chỉ là tùy chọn kiểm tra khởi động/thoát tự động, được ẩn khỏi trợ giúp thông thường.

## Phạm vi tự động

| Nhóm | Nội dung kiểm tra |
|---|---|
| Thời gian | Roundtrip 0/1 ms/>1 giờ/100 giờ; sai định dạng, phút/giây ngoài phạm vi, số âm/sai kiểu. |
| Khoảng cắt | IN≥OUT, âm, vượt nguồn, padding âm/NaN; clamp padding; nhóm/mode/review/UUID không hợp lệ; sự kiện thiếu một đầu, đảo đầu, ngoài clip. |
| Probe | Đọc metadata fixture H.264/AAC, rational FPS; file mất, codec lỗi mô phỏng, không có video stream. |
| FFmpeg arguments | Đường dẫn có dấu, khoảng trắng, ký tự shell là một argument; audio tùy chọn; không shell=True. |
| Xuất thực | Fast MKV và Precise MP4; nhiều clip; không audio; tên dài có dấu; video >1 giờ; nguồn start timestamp=5s; VFR được xác nhận từ khoảng cách timestamp frame. |
| Xác minh output | FFmpeg exit 0 nhưng không sinh file hợp lệ bị từ chối; FFprobe lỗi, độ dài sai dung sai, FFmpeg nonzero đều failed và dọn temp. |
| An toàn | So sánh SHA-256/size/mtime và đường dẫn nguồn trước/sau; thử trùng UUID không ghi đè clip đã có; UUID chứa ../ bị từ chối. |
| Hủy | Hủy trước tác vụ và hủy FFmpeg thật đang chạy với input throttled; không còn clip dở/temp. |
| Lỗi IO | Thiếu dung lượng, PermissionError, ENOSPC được mô phỏng; đầu ra là file thay vì thư mục được thử thực; mất nguồn và nguồn đổi size được phát hiện. |
| SQLite | Migration version, từ chối DB mới hơn, unique canonical path, CRUD/foreign key/transaction, pending→processing→failed, phục hồi job gián đoạn, persistence khi reopen. |
| CSV | BOM UTF-8-SIG, đọc lại tiếng Việt/nhiều dòng, mili giây dạng số nguyên, event NULL; chống ghi CSV lên nguồn đã đăng ký. |
| UI | Mở/phát/dừng/tua file có dấu; file hỏng; giữ ghi chú; IN/OUT/sự kiện/padding sau reopen; lọc bảng; timer heartbeat khi worker chạy; chống bấm xuất lặp; session lock; failed job có lỗi trong SQLite; nguồn mất giữ lịch sử. |
| Media/stress | Nhận frame hợp lệ từ QVideoSink; chuyển lựa chọn nhanh 25 lần với tối đa một probe; preview tự dừng; I/O/Space khi đang nhập ghi chú không chặn nhập. |

## Kiểm tra desktop và hiện vật

`scripts/smoke_desktop.py` tạo nguồn tổng hợp, mở cửa sổ, chờ Qt giải mã frame thật, xuất hai chế độ, xác nhận hai bản ghi completed, xuất CSV và so SHA-256 nguồn. Script ghi vào thư mục chỉ định:

- `report.json`: kết quả, vị trí player và metadata clip.
- `desktop.png`, `desktop-screen.png` (khi dùng native): ảnh kiểm tra bố cục/chữ.
- `decoded-frame.png`: ảnh từ frame mà Qt giải mã, giúp kiểm tra pipeline video độc lập với việc chụp native video surface.
- `clip_inventory.csv`, các clip mẫu và SQLite kiểm thử.

Đã xem ảnh giao diện Windows với chữ tiếng Việt và ảnh frame tổng hợp. Ảnh chụp widget/window có thể không chứa bề mặt video native; không dùng vùng trống trong ảnh đó để suy luận decoder không chạy. Frame hợp lệ và ảnh decoded được kiểm tra riêng. Sau kiểm tra layout, nút xuất/xem trước/hủy đã được ghim ngoài vùng nhập cuộn để luôn truy cập nhanh.

Hiện vật trong `test-artifacts` được `.gitignore` bỏ qua; không phải dữ liệu sản phẩm hay video người dùng.

## Điều chỉnh môi trường kiểm thử và lỗi đã sửa

- Chuẩn hóa snapshot source path trên Windows để CSV/lịch sử không khác canonical path chỉ do chữ hoa/thường.
- Lưu bản nháp trước đổi nguồn, giữ pending seek khi nguồn chưa load xong, lưu metadata trước worker, ghi trạng thái lỗi khi nguồn biến mất trước xuất.
- Giải phóng media source/output khi đóng; giới hạn một probe và loại kết quả cũ bằng generation token; test teardown chờ worker hoàn tất để không hủy QThread đang chạy.
- `--help` đã được sửa để in tiếng Việt UTF-8 trong terminal Windows có code page khác UTF-8.
- Qt 6.12.0 có native abort không thường xuyên trong quá trình kiểm thử; thay platform/capture chưa loại bỏ hoàn toàn. Các bản 6.8.3/6.10.3 giúp tái hiện rõ treo tại `QMediaPlayer.stop()` ngay sau seek ở trạng thái pause. Đã bỏ lệnh stop dư thừa khi đổi/đóng nguồn, dùng `setSource(QUrl())` để Qt ngừng I/O và giải phóng nguồn, đồng thời dùng `@Slot`/QueuedConnection cho kết quả worker và callback media. Cấu hình cuối pin **6.10.3**, đã qua 60 tests và desktop smoke. Chưa khẳng định nguyên nhân nội bộ hay một lỗi upstream cụ thể. Pytest dùng capture=sys để không thay OS file descriptor khi multimedia threads đang ghi log.
- Windows test mặc định dùng platform native. `offscreen` Windows trên host này hiển thị font thành ô vuông; không dùng ảnh offscreen để nghiệm thu chữ. Linux không có DISPLAY/WAYLAND sẽ chọn offscreen cho test, nhưng chưa chạy trên Ubuntu ở phiên này.

## Chưa xác minh / giới hạn thực tế

- Chưa chạy Ubuntu, chưa thử nhiều GPU/driver, codec/profiles đặc biệt, rotation metadata phức tạp, HDR hoặc filesystem mạng.
- Thiếu quyền/hết đĩa được kiểm tra bằng mô phỏng và IO lỗi có kiểm soát, không thay quyền thư mục hệ thống hay cố lấp đầy ổ đĩa thật.
- Đã kiểm tra định dạng/nội dung CSV bằng Python; **chưa mở bằng Microsoft Excel**.
- Không xác minh frame đầu của clip đối chiếu từng frame nguồn. Fast luôn approximate; Precise cũng không tuyên bố frame-accurate. Dung sai và NULL/unknown được ghi trong README/ARCHITECTURE.
- Đã thử riêng `Video_000.mp4` ngày 05/11 theo yêu cầu người dùng; chưa benchmark video nhiều GB hoặc thư viện hàng trăm nghìn clip. Video >1 giờ trong bộ tự động dùng fixture nhỏ để kiểm tra timestamp/seek, không đại diện tải xử lý 4K nhiều giờ.
- Chưa có installer; chạy từ source với `.venv`. Khôi phục hard crash chỉ đánh dấu job failed và giữ file chưa xác minh, không tự nhận completed hoặc xóa dữ liệu.

## Tự nghiệm thu với video thực tế

Sau khi cài, chọn một video đại diện cho camera của bạn, thử play/seek/âm thanh, đặt một khoảng ngắn, xuất cả Fast/Precise vào thư mục riêng rồi xem lại. Kiểm tra đường dẫn/size/mtime nguồn, lịch sử, CSV và mở lại ứng dụng. Với codec không hỗ trợ, thông báo lỗi phải rõ và nguồn vẫn giữ nguyên. Thử bấm hủy trên một tác vụ đủ dài; chờ worker kết thúc trước khi đóng.
