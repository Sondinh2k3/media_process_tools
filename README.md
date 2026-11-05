# Video Dataset Tool V1

Ứng dụng desktop **Python 3.11+ / PySide6**, dùng để xem video, chọn khoảng thời gian, cắt clip và quản lý nguồn dữ liệu. Giao diện và hướng dẫn bằng tiếng Việt. Nhãn `positive` chỉ biểu thị **nghi vấn cần xem xét**, không phải kết luận vi phạm.

PySide6 được pin **6.10.3** trong `pyproject.toml` để tái lập môi trường kiểm chứng. Không tự nâng Qt trước khi chạy lại bộ kiểm thử multimedia.

## Chạy ngay trong workspace này (Windows)

Môi trường `.venv` đã được cài và bộ FFmpeg/FFprobe dùng kiểm thử nằm trong `.tools`. Từ terminal VS Code tại thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m video_dataset_tool
```

Để lưu database, bản nháp, thiết lập và log vào một dataset riêng:

```powershell
.\.venv\Scripts\python.exe -m video_dataset_tool --data-dir "E:\tools\Data_process\my_dataset\app_data"
```

Thư mục nguồn và thư mục clip xuất được chọn độc lập trong giao diện. Thư mục video không bị di chuyển hay đổi tên. Mỗi `--data-dir` chỉ cho phép một cửa sổ cùng lúc.

## Cài mới trên Windows

1. Cài Python 3.11 trở lên và bảo đảm lệnh `python --version` hoạt động.
2. Cài bản FFmpeg có cả `ffmpeg.exe`, `ffprobe.exe`, codec `libx264` và AAC từ [trang tải FFmpeg](https://ffmpeg.org/download.html). Thêm thư mục `bin` của bản tải vào PATH, rồi mở lại terminal VS Code. Kiểm tra:

```powershell
ffmpeg -version
ffprobe -version
```

3. Tại thư mục chứa `pyproject.toml`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m video_dataset_tool
```

Các lệnh gọi Python trong `.venv` trực tiếp nên không cần đổi Execution Policy của PowerShell. Nếu đã kích hoạt `.venv`, có thể dùng `python -m video_dataset_tool`.

## Cài mới trên Ubuntu

**Ubuntu chưa được chạy kiểm chứng trong môi trường phát triển hiện tại.** Các bước dưới đây dành cho Ubuntu có desktop và Python 3.11+ (ví dụ Python hệ thống trên Ubuntu 24.04):

```bash
sudo apt update
sudo apt install python3 python3-venv ffmpeg libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-xinerama0 libpulse0
python3 --version
ffmpeg -version
ffprobe -version
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m video_dataset_tool
```

Không chạy GUI trong máy Linux chỉ có terminal nếu chưa cấu hình môi trường đồ họa. Phần kiểm thử có thể dùng `QT_QPA_PLATFORM=offscreen`; xem [kế hoạch kiểm thử](docs/TEST_PLAN.md).

## Quy trình sử dụng

1. **Mở file** hoặc **Mở thư mục**. Thư mục được quét một cấp, theo các đuôi MP4, MOV, MKV, AVI, M4V, WebM, MTS, M2TS, TS. Bấm tên video để phát; thông số thời lượng, FPS hữu tỷ và kích thước được đọc bằng FFprobe.
2. Phát/dừng, kéo timeline hoặc tua ±1 giây. Đồng hồ hiển thị vị trí do backend Qt báo lại. Hai nút `≈1 frame` chỉ di chuyển xấp xỉ theo FPS.
3. **Đặt IN/OUT** tại vị trí hiện tại hoặc nhập `HH:MM:SS.mmm`. Chỉnh đệm trước/sau nếu cần; ứng dụng giới hạn đệm ở đầu/cuối video. **Xem trước khoảng xuất** để kiểm tra.
4. Chọn nhóm, nhập loại vật và ghi chú. Khoảng **sự kiện** là tùy chọn, mặc định trống; nếu nhập thì cần cả hai đầu và nằm trong khoảng clip xuất.
5. Chọn **Thư mục xuất**, chọn Fast hoặc Precise, bấm **Xuất clip**. Có tiến độ và nút hủy. Mỗi lần chỉ chạy một tác vụ; có thể tiếp tục xem/chỉnh bản nháp trong lúc xử lý.
6. Xem **Lịch sử clip**, lọc theo video/nhóm/trạng thái hoặc tìm trong tên nguồn, loại vật, ghi chú, UUID. Chọn clip rồi mở thư mục hoặc xem chi tiết. **Xuất CSV** ghi toàn bộ lịch sử, kể cả tác vụ thất bại/hủy.

Bản nháp được lưu theo từng video sau khi ngừng nhập khoảng 350 ms, mỗi 2 giây, trước khi đổi video/xuất và khi đóng. Lần mở lại khôi phục thư viện, bản nháp, vị trí phát, thư mục xuất và bố cục. **Thiết lập** cấu hình chế độ cắt và padding mặc định cho video chưa có bản nháp.

## Hai chế độ cắt

| Chế độ | Kết quả | Giới hạn |
|---|---|---|
| Fast | MKV, sao chép video/audio, không mã hóa lại | Có thể chứa phần trước IN hoặc lệch thời lượng do keyframe/timestamp. Luôn lưu `approximate`. |
| Precise | MP4, H.264 (`libx264`, CRF 18) và AAC nếu có audio | Mã hóa lại, chậm hơn; hướng tới frame gần yêu cầu, không bảo đảm chính xác tuyệt đối. |

Không crop hoặc resize. Fast dùng MKV để hỗ trợ nhiều codec và audio hơn MP4. Không tự chuyển sang mã hóa lại nếu Fast lỗi; người dùng có thể chọn Precise. Codec/định dạng đặc biệt có thể không được hỗ trợ.

Chỉ báo hoàn tất khi FFmpeg thành công, file có ít nhất 128 byte và FFprobe đọc được video có thời lượng hợp lệ. Dung sai: **Fast = max(3 giây, 10% độ dài yêu cầu)**; **Precise = max(150 ms, 2 chu kỳ frame theo FPS)**, hoặc 250 ms khi không có FPS. Đây là kiểm tra độ dài, không phải xác minh chính xác frame đầu. `actual_start_ms` để NULL, `actual_duration_ms` lấy từ FFprobe; Precise lưu `cut_precision=unknown` vì chưa xác minh ánh xạ frame về nguồn.

## Bảo toàn và lưu trữ dữ liệu

- Video nguồn chỉ được đọc. Tên clip gồm tên nguồn rút gọn + UUID, chia vào thư mục nhóm. File tạm thuộc ứng dụng được kiểm tra rồi mới công bố; không ghi đè clip cũ.
- SQLite lưu UUID nguồn, đường dẫn canonical, size/mtime, thông số video, khoảng yêu cầu, khoảng sự kiện, ghi chú, chế độ, trạng thái và lỗi. Mỗi clip giữ thêm snapshot đường dẫn/size/mtime nguồn.
- IN/OUT sau khi cộng padding là `requested_in_ms`/`requested_out_ms`. Ô IN/OUT và padding gốc được giữ trong bản nháp. Ứng dụng không tự điền khoảng sự kiện bằng khoảng cắt.
- Mặc định Windows: `%LOCALAPPDATA%\VideoDatasetTool`; Linux: `${XDG_DATA_HOME:-~/.local/share}/VideoDatasetTool`. Có thể đổi bằng `--data-dir` hoặc biến môi trường `VIDEO_DATASET_DATA_DIR`.
- File `dataset.sqlite3`, bảng thiết lập/bản nháp và `application.log` nằm trong thư mục dữ liệu. Log được xoay vòng (2 MB, giữ 2 bản cũ), chỉ lưu cục bộ. Đóng ứng dụng trước khi sao lưu toàn bộ thư mục dữ liệu; clip nằm ở thư mục xuất độc lập cũng cần được sao lưu.
- **Kiểm tra nguồn** cập nhật nguồn mất/đã thay đổi và mở lại nguồn đang chọn. Mất file không xóa lịch sử. Không có chức năng tự tìm/di chuyển video đã thất lạc trong V1.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\ruff.exe format --check src tests scripts
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\smoke_desktop.py --output-dir test-artifacts\desktop
```

Trên Ubuntu dùng `.venv/bin/python -m pytest -q` và `.venv/bin/ruff check src tests scripts`. Video kiểm thử được sinh bằng FFmpeg, không dùng video của người dùng. Nếu thiếu FFmpeg/FFprobe, các test phụ thuộc fixture video sẽ được skip, không được hiểu là đã xác minh export. Chi tiết kết quả và các giới hạn: [docs/TEST_PLAN.md](docs/TEST_PLAN.md).

## Xử lý lỗi nhanh

| Hiện tượng | Cách xử lý |
|---|---|
| Thiếu FFmpeg/FFprobe | Thêm `bin` vào PATH và mở lại. Có thể chỉ định đường dẫn executable bằng `VIDEO_DATASET_FFMPEG` / `VIDEO_DATASET_FFPROBE`; ứng dụng cũng tìm trong `.tools` ở source checkout. |
| FFprobe đọc được nhưng Qt không phát | Kiểm tra codec, driver, Qt Multimedia và FFmpeg. Vẫn có thể thử xuất clip nếu metadata hợp lệ. |
| Fast sai khoảng nhiều hoặc lỗi container | Chọn Precise; xem lại clip thực tế trước khi sử dụng. |
| Không ghi được clip/CSV/database | Kiểm tra quyền, dung lượng, đường dẫn và ổ đĩa. Ước lượng dung lượng chỉ giúp phát hiện sớm; không bảo đảm kích thước sau mã hóa. |
| Dataset đang mở | Đóng cửa sổ sử dụng cùng thư mục dữ liệu, hoặc chạy với `--data-dir` khác. Không xóa lock khi cửa sổ kia còn hoạt động. |
| Nguồn mất/đã đổi | Khôi phục file tại đường dẫn cũ bằng thao tác của bạn, bấm Kiểm tra nguồn; ứng dụng không tự sửa nguồn. |
| Tác vụ từ phiên trước bị gián đoạn | Lịch sử ghi `failed`. Kiểm tra log/clip còn lại rồi tạo tác vụ xuất mới. Không tự đánh dấu thành công hoặc xóa clip. |

Tài liệu chi tiết: [hướng dẫn sử dụng](docs/USER_GUIDE.md), [kiến trúc](docs/ARCHITECTURE.md), [báo cáo kiểm thử](docs/TEST_PLAN.md). V1 không có AI, trích frame hàng loạt, gán nhãn nâng cao hoặc cloud.
