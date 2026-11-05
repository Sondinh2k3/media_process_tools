# CODEX IMPLEMENTATION SPEC — Video Dataset Tool (V1)

> **Tài liệu giao việc trực tiếp cho Codex.** Hãy đọc toàn bộ trước khi sửa mã. Thực hiện và kiểm thử ứng dụng trong repository hiện tại. Nếu repository chưa có mã nguồn, khởi tạo dự án mới. Không chỉ đưa ra đề xuất hay code mẫu: cần triển khai ứng dụng V1 hoạt động thực sự.
>
> **Ngôn ngữ giao diện và tài liệu hướng dẫn:** Tiếng Việt. **Ngôn ngữ mã nguồn, tên biến và API:** Tiếng Anh.
>
> **Ưu tiên:** độ tin cậy của dữ liệu, thao tác nhanh, dễ sử dụng, dễ mở rộng. Không thêm AI/model inference, chức năng gán nhãn polygon hoặc tích hợp cloud trong V1.

## 1. Bối cảnh và mục tiêu

Người dùng đang nghiên cứu bài toán **phát hiện tình huống nghi lấn chiếm lòng đường** bằng camera gắn trên phương tiện (mô phỏng góc nhìn camera trên xe buýt). Dữ liệu nguồn là các video quay thực tế tại Việt Nam. Trước mắt cần **xem video, đánh dấu khoảng thời gian có tình huống hữu ích, cắt clip và lưu thông tin nguồn**, qua đó chuẩn bị dữ liệu cho phân tích, chọn frame, gán nhãn, huấn luyện và đánh giá sau này.

Công cụ **không tự quyết định có vi phạm pháp luật hay không**. Nhãn `positive` trong V1 mang nghĩa *nghi lấn chiếm/có tình huống cần xem xét*, không phải kết luận vi phạm.

### Mục tiêu V1 (bắt buộc)

1. Ứng dụng desktop Python, chạy trực tiếp từ VS Code bằng `python -m video_dataset_tool` và có cửa sổ riêng.
2. Mở một video hoặc thư mục video; hiển thị danh sách video và các thông số cơ bản.
3. Xem video trong ứng dụng: phát/tạm dừng, tua, kéo timeline, xem thời gian hiện tại/tổng thời lượng, chỉnh tốc độ khi backend hỗ trợ, chỉnh âm lượng/tắt tiếng.
4. Đánh dấu **IN** và **OUT** theo vị trí phát hiện tại; cho phép sửa thời điểm bằng ô nhập; xem trước khoảng chọn.
5. Nhập nhóm tình huống và ghi chú; xuất clip vào thư mục cấu hình; **giữ nguyên video gốc**.
6. Lưu danh mục clip và thông tin liên kết tới video nguồn vào cơ sở dữ liệu SQLite; có thể xuất CSV.
7. Có danh sách clip đã xuất, nút mở thư mục chứa clip và khôi phục trạng thái làm việc gần nhất.
8. Chống trùng lặp, kiểm tra lỗi đầu vào/đầu ra, thông báo rõ khi xuất thất bại; giao diện không bị treo khi cắt video.
9. Có kiểm thử tự động cho logic cốt lõi, hướng dẫn cài đặt/vận hành cho Windows và Ubuntu.

### Ngoài phạm vi V1 (không thực hiện)

- Tự động phát hiện vật thể lấn chiếm bằng AI; tự động đề xuất thời điểm cắt.
- Trích frame hàng loạt, lọc ảnh mờ/trùng, nhận diện cảnh, tính GPS tự động (để dành V2).
- Vẽ bounding box/polygon/mask, xuất CVAT/YOLO/Cityscapes (để dành V3).
- Đồng bộ cloud, nhiều người dùng, tài khoản, gán nhãn cộng tác.
- Tạo extension chạy *bên trong tab VS Code*. V1 là ứng dụng desktop **được chạy từ VS Code**.

## 2. Nguyên tắc bảo toàn dữ liệu (bắt buộc)

- **Raw video immutable:** tuyệt đối không sửa, đổi tên, di chuyển, ghi đè hoặc xóa video gốc.
- Clip xuất là **dữ liệu dẫn xuất**; phải lưu `source_video_id`, đường dẫn nguồn, `requested_in_ms`, `requested_out_ms`, chế độ cắt, đường dẫn clip và trạng thái xuất.
- Tách biệt **khoảng xuất clip** với **thời gian thực sự xuất hiện tình huống**. V1 cho phép lưu `event_start_ms` / `event_end_ms` tùy chọn (mặc định để trống); không mặc định chúng chính là IN/OUT.
- Không ghi đè clip cũ. Khi trùng tên, dùng định danh duy nhất hoặc báo lỗi và tạo tên mới an toàn.
- Metadata phải được lưu bền vững; nếu export lỗi, bản ghi phải hiển thị trạng thái `failed` và lý do, không báo thành công.
- Có thể đọc được file và đường dẫn chứa ký tự tiếng Việt, dấu cách; hỗ trợ Windows và Linux.
- Không xóa dữ liệu người dùng do lỗi đọc file hoặc tiến trình FFmpeg.
- Tránh dùng filename làm khóa chính; dùng UUID. Với nguồn, lưu cả `source_path` và thông tin nhận diện (size, mtime, tùy chọn hash khi cần). Không tính full hash bắt buộc với mọi video lớn ở V1.
- Không đưa video thật của người dùng vào repo, log công khai hoặc test fixtures.

## 3. Công nghệ đề xuất

| Thành phần | Lựa chọn V1 | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python 3.11+ | Ưu tiên code rõ ràng, type hints |
| UI | PySide6 + Qt Widgets | Giao diện desktop, không xây web server |
| Phát video | `QMediaPlayer` + `QVideoWidget` | Có fallback/thông báo nếu codec không hỗ trợ |
| Metadata video | `ffprobe` (JSON output) | Gọi bằng `subprocess`, xử lý lỗi có cấu trúc |
| Cắt video | `ffmpeg` | Worker thread hoặc QProcess, không chặn UI |
| Database | SQLite (`sqlite3`) | Migration có version, transaction |
| Export bảng | CSV UTF-8-SIG | Mở tốt bằng Excel tiếng Việt |
| Tests | `pytest`, `pytest-qt` (nếu phù hợp) | Mock bên ngoài ở unit test; smoke test bằng file tổng hợp |
| Packaging (sau khi chạy tốt) | PyInstaller hoặc hướng dẫn source-run | Không ưu tiên trước chức năng cốt lõi |

**Quan trọng:** Không giả định Qt multimedia mở được mọi video/codec. Khi file không phát được, hiển thị lỗi dễ hiểu và đề xuất kiểm tra codec/cài FFmpeg. Có thể cân nhắc backend player khác ở giai đoạn sau, nhưng không thay đổi stack nếu chưa xác định lỗi thực tế.

## 4. Thiết kế giao diện

Bố cục 3 khu vực, có thể resize:

```text
┌────────────────────────────────────────────────────────────────────────────────┐
│ Video Dataset Tool  [Mở file] [Mở thư mục] [Thư mục xuất] [Thiết lập]          │
├────────────────┬───────────────────────────────────────┬───────────────────────┤
│ DANH SÁCH VIDEO│ TRÌNH XEM VIDEO                        │ THÔNG TIN CLIP         │
│ ▸ VID_001      │                                       │ IN  00:01:10.200      │
│ ▸ VID_002      │   Video preview                       │ OUT 00:01:28.500      │
│ ...            │                                       │ Nhóm: [positive ▼]   │
│                │                                       │ Loại vật: [tùy chọn] │
│                │                                       │ Mô tả: [...]         │
│                │                                       │ Chế độ: [Fast/Precise]│
│                │                                       │ [Xuất clip]           │
├────────────────┴───────────────────────────────────────┴───────────────────────┤
│ [▶] [◀ frame] [frame ▶]  00:01:23.480 / 00:05:42.000  [tốc độ] [âm lượng] │
│ ───────────────── [IN]══════●═════════[OUT] ──────────────────────────────── │
├────────────────────────────────────────────────────────────────────────────────┤
│ CLIP ĐÃ XUẤT   | Tên | Nhóm | Video gốc | IN | OUT | Trạng thái | Mở thư mục │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Yêu cầu tương tác

- Khi nhấn vào video ở danh sách: mở phát và cập nhật thời lượng, FPS, kích thước hình (nếu lấy được).
- Thanh thời gian hiển thị vị trí phát; khi kéo phải cập nhật chính xác vị trí do trình phát **thực tế xác nhận**, không giả định seek đã chính xác đến frame.
- IN/OUT có biểu thị trực quan trên timeline; đồng thời cho phép nhập thời gian dạng `HH:MM:SS.mmm`.
- Hiển thị độ dài clip dự kiến; cảnh báo khi IN ≥ OUT, ngoài khoảng video, hoặc đường dẫn đầu ra không hợp lệ.
- Hiển thị tiến độ đang xử lý, cho phép hủy tác vụ nếu khả thi, và trạng thái thành công/thất bại.
- Lưu ghi chú và lựa chọn trước khi xuất; tránh mất nội dung khi đổi video ngoài ý muốn.
- Các dialog lỗi phải rõ ràng và không chứa stack trace cho người dùng cuối (chi tiết lỗi ghi log cục bộ).
- Danh sách clip có thể lọc theo video nguồn, nhóm, trạng thái.

### Phím tắt đề xuất

| Phím | Hành động |
|---|---|
| `Space` | Play/Pause khi không nhập liệu |
| `I` | Đặt IN tại vị trí phát |
| `O` | Đặt OUT tại vị trí phát |
| `Left` / `Right` | Tua ngắn (mặc định 1 giây), khi không nhập liệu |
| `Shift+Left` / `Shift+Right` | Tua dài (mặc định 5 giây) |
| `Ctrl+E` | Xuất clip sau khi kiểm tra dữ liệu |
| `Ctrl+O` | Mở file video |
| `Ctrl+Shift+O` | Mở thư mục video |

**Frame stepping:** Nếu backend hỗ trợ seek chính xác theo frame, cung cấp phím đi 1 frame. Nếu không có bảo đảm, phải ghi rõ đó là *di chuyển xấp xỉ*, không quảng cáo "frame-accurate". Tính năng frame stepping chính xác là nâng cấp sau nếu cần.

## 5. Phân loại tình huống

Bốn nhóm cố định V1:

| Code | Nhãn hiển thị | Định nghĩa công việc |
|---|---|---|
| `positive` | Có tình huống nghi lấn chiếm | Có đối tượng hoặc khu vực cần kiểm tra khả năng chiếm dụng lòng đường; **chưa kết luận vi phạm** |
| `hard_negative` | Dễ nhận nhầm | Trường hợp trông giống lấn chiếm nhưng được xác định không thuộc nhóm nghi vấn theo quy tắc nội bộ |
| `normal` | Giao thông bình thường | Không ghi nhận tình huống nghi vấn trong đoạn được chọn |
| `uncertain` | Chưa đủ thông tin | Không đủ căn cứ kết luận, bị che khuất hoặc mơ hồ ranh giới đường/vỉa hè |

Nhập thêm trường tùy chọn `object_type` dưới dạng text hoặc danh sách gợi ý (ví dụ: vật liệu xây dựng, hàng hóa, quầy hàng, xe đẩy, vật dụng, bóng đổ, cây xanh, xe dừng), **không hardcode nó thành nhãn AI huấn luyện**. Thêm `notes` và tùy chọn `review_status` (`unreviewed`, `reviewed`) để phục vụ tương lai.

## 6. Quy tắc cắt video

### 6.1. Hai chế độ

**Fast Cut (mặc định khi khảo sát)**

- Dùng stream copy, **không mã hóa lại**, nhằm cắt nhanh và tránh giảm chất lượng do re-encode.
- Điểm cắt có thể lệch so với thời gian yêu cầu vì keyframe/timestamp. Không được báo rằng kết quả chính xác tuyệt đối.
- Lưu riêng `requested_in_ms`, `requested_out_ms`, `actual_start_ms`, `actual_duration_ms` khi xác định được; nếu không xác minh được chính xác thì lưu `NULL`, kèm cảnh báo `cut_precision = 'approximate'`.

Ví dụ lệnh mang tính tham khảo (Codex cần tạo argument list an toàn, không dùng `shell=True`):

```bash
ffmpeg -hide_banner -nostdin -y -ss 70.2 -i input.mp4 -t 18.3 -map 0:v:0 -map 0:a? -c copy output.mp4
```

**Precise Cut (khi cần giới hạn thời gian sát yêu cầu)**

- Giải mã và mã hóa lại video, seek phù hợp và bảo đảm timestamp được căn chỉnh; có thể mất thời gian và không thể bảo toàn bitstream gốc.
- Chọn codec/output hợp lý (ví dụ H.264 + AAC trong MP4 khi tương thích); ghi rõ rằng `precise` nghĩa là hướng tới điểm cắt gần frame mong muốn trong giới hạn định dạng và decoder, **không tự động bảo đảm độ chính xác tuyệt đối**.
- Nếu âm thanh không có thì không lỗi; giữ audio nếu có và phù hợp.
- Không thực hiện crop hoặc resize hình ảnh.
- Tên file nên chứa `clip_id` và rút gọn tên nguồn; không phụ thuộc hoàn toàn timestamp.

### 6.2. Kiểm tra sau export

- FFmpeg exit code bằng 0 **chưa đủ**. Kiểm tra tồn tại file, kích thước hợp lý và chạy `ffprobe` xác nhận đọc được, có video stream và thời lượng phù hợp kỳ vọng với dung sai được tài liệu hóa.
- Nếu export bị dừng/hỏng: chuyển trạng thái `failed`; dọn file tạm do ứng dụng tạo ra, nhưng không xóa clip cũ hoặc dữ liệu gốc.
- Dùng file tạm trong thư mục đích rồi `os.replace()` sang tên duy nhất sau khi kiểm tra; tránh đưa file xuất dở vào danh mục thành công.
- Khi người dùng bấm export nhiều lần, không chạy trùng một job; xử lý queue hoặc khóa nút export đối với tác vụ hiện tại.
- Cho phép người dùng chỉnh padding trước/sau khi cắt (mặc định 0 giây; gợi ý 3–5 giây mỗi bên). Nếu có padding, ghi riêng `event_start_ms`/`event_end_ms` nếu người dùng đã nhập; không ghi đè khoảng sự kiện bằng khoảng clip.

## 7. Đề xuất cấu trúc thư mục dữ liệu

Không ép người dùng di chuyển các video hiện có. Cho phép cấu hình thư mục nguồn và thư mục đích độc lập.

```text
road_dataset/
├── raw_videos/                # video gốc — không sửa trực tiếp
│   ├── VID_001.mp4
│   └── VID_002.mp4
├── clips/
│   ├── positive/
│   ├── hard_negative/
│   ├── normal/
│   └── uncertain/
├── metadata/
│   └── clip_inventory.csv    # export từ SQLite khi người dùng yêu cầu
└── app_data/                  # chỉ dùng khi cấu hình dự án lưu vào đây
    └── dataset.sqlite3
```

Ưu tiên đặt database mặc định ở thư mục dữ liệu ứng dụng của hệ điều hành; nếu mở một "project dataset" thì cho phép dùng DB trong thư mục project khi người dùng chọn. Không bắt buộc thư mục video gốc nằm trong `road_dataset`.

## 8. Mô hình dữ liệu SQLite V1

Thiết kế migration (ví dụ `PRAGMA user_version`) và tối thiểu các bảng:

### `source_videos`

- `id TEXT PRIMARY KEY` (UUID)
- `source_path TEXT NOT NULL`
- `display_name TEXT`
- `file_size_bytes INTEGER`
- `mtime_ns INTEGER`
- `duration_ms INTEGER`
- `fps_num INTEGER`, `fps_den INTEGER` (FPS là số hữu tỷ, không chỉ float)
- `width INTEGER`, `height INTEGER`
- `video_codec TEXT`, `audio_codec TEXT`
- `created_at TEXT`, `last_seen_at TEXT`
- Unique strategy hợp lý cho đường dẫn canonical; nếu file biến mất phải giữ lịch sử và báo `missing`, không xóa.

### `clips`

- `id TEXT PRIMARY KEY` (UUID)
- `source_video_id TEXT NOT NULL REFERENCES source_videos(id)`
- `requested_in_ms INTEGER NOT NULL`, `requested_out_ms INTEGER NOT NULL`
- `event_start_ms INTEGER NULL`, `event_end_ms INTEGER NULL`
- `actual_start_ms INTEGER NULL`, `actual_duration_ms INTEGER NULL`
- `category TEXT NOT NULL`
- `object_type TEXT NULL`, `notes TEXT NULL`
- `review_status TEXT DEFAULT 'unreviewed'`
- `cut_mode TEXT NOT NULL` (`fast`, `precise`)
- `cut_precision TEXT` (`approximate`, `verified`, `unknown`)
- `output_path TEXT NULL`
- `status TEXT NOT NULL` (`pending`, `processing`, `completed`, `failed`, `cancelled`)
- `error_message TEXT NULL`
- `created_at TEXT`, `updated_at TEXT`

### `app_settings` (hoặc `QSettings`)

- `last_opened_video_id`
- `last_source_dir`
- `output_root_dir`
- `default_cut_mode`
- `default_padding_before_s`, `default_padding_after_s`
- `window_geometry`

Nếu chọn `QSettings` thì chỉ dùng để lưu setting cục bộ; dữ liệu clip/video vẫn phải nằm trong SQLite.

### CSV export

Các cột tối thiểu: `clip_id,source_video_id,source_path,clip_path,requested_in_ms,requested_out_ms,event_start_ms,event_end_ms,category,object_type,notes,cut_mode,status,created_at`. Xuất `UTF-8-SIG`, không làm mất định dạng thời gian mili giây hoặc ký tự tiếng Việt. Chỉ export bảng; không dùng CSV làm nguồn dữ liệu chính.

## 9. Cấu trúc repository dự kiến

```text
video-dataset-tool/
├── README.md
├── pyproject.toml
├── .gitignore
├── src/
│   └── video_dataset_tool/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       ├── ui/
│       │   ├── main_window.py
│       │   ├── video_player.py
│       │   ├── clip_editor.py
│       │   └── clip_table.py
│       ├── core/
│       │   ├── models.py
│       │   ├── timecode.py
│       │   ├── validators.py
│       │   └── paths.py
│       ├── services/
│       │   ├── ffmpeg_service.py
│       │   ├── video_probe.py
│       │   └── export_service.py
│       ├── storage/
│       │   ├── database.py
│       │   ├── migrations.py
│       │   └── repositories.py
│       └── workers/
│           └── export_worker.py
├── tests/
│   ├── test_timecode.py
│   ├── test_clip_validation.py
│   ├── test_database.py
│   ├── test_export_service.py
│   └── test_smoke.py
└── docs/
    ├── ARCHITECTURE.md
    ├── USER_GUIDE.md
    └── TEST_PLAN.md
```

Có thể tinh chỉnh cấu trúc nếu có lý do kỹ thuật rõ ràng; không tạo quá nhiều abstraction khi chưa cần.

## 10. Quy trình triển khai cho Codex

**Phải triển khai tuần tự; sau mỗi milestone chạy được phần tương ứng và kiểm thử trước khi chuyển bước.**

### M1 — Khởi tạo và mở video

- Tạo Python package, cấu hình dependencies và test/lint cơ bản.
- Kiểm tra FFmpeg/FFprobe trên PATH khi ứng dụng khởi động, thông báo cách cài nếu thiếu.
- Dựng main window, chọn video hoặc thư mục, danh sách file và player.
- Đọc metadata từ `ffprobe` và hiển thị thời lượng, FPS, độ phân giải.
- Play, pause, seek, timeline và thời gian định dạng `HH:MM:SS.mmm`.

**Done khi:** mở được video thử, xem/tua được, không crash khi đổi file hoặc mở file lỗi.

### M2 — Chọn khoảng thời gian và cắt clip

- Nút và phím tắt IN/OUT, sửa thời gian thủ công.
- Kiểm tra khoảng hợp lệ, nhóm tình huống và ghi chú.
- Tạo worker xuất Fast Cut; quản lý FFmpeg process, cancel/error/progress tối thiểu.
- Tạo Precise Cut; kiểm tra bằng ffprobe sau export.
- Xuất theo thư mục nhóm, đặt tên không trùng và không ghi đè.

**Done khi:** cắt được nhiều đoạn từ một video; giao diện vẫn phản hồi; không tạo clip completed khi export thất bại.

### M3 — Lưu lịch sử và quản lý dữ liệu

- SQLite schema + migration; lưu video và clip.
- Danh sách clip, tìm/lọc, mở thư mục chứa clip.
- Lưu cấu hình lần cuối, khôi phục danh sách sau khi đóng/mở lại.
- Export CSV UTF-8-SIG.
- Cập nhật tình trạng video bị mất đường dẫn mà vẫn giữ lịch sử clip.

**Done khi:** đóng và mở lại ứng dụng không mất dữ liệu; xuất CSV đầy đủ, đọc được tiếng Việt.

### M4 — Hoàn thiện và kiểm thử

- Kiểm tra trên Windows và Ubuntu (nếu môi trường hiện tại chỉ có một OS thì tự động test được OS đó, và ghi rõ OS chưa xác minh; không tự nhận đã test cả hai).
- Kiểm thử filename tiếng Việt, file dài, video không có âm thanh, codec không hỗ trợ, hủy export, thiếu dung lượng/thiếu quyền, mất file nguồn.
- Tài liệu cài đặt, hướng dẫn người dùng và giới hạn kỹ thuật.
- Có thể bổ sung đóng gói nếu không ảnh hưởng tiến độ/độ tin cậy của V1.

**Done khi:** người dùng có thể dùng ứng dụng trên video thật, và các chức năng cốt lõi có test/kiểm tra rõ ràng.

## 11. Tiêu chí nghiệm thu (acceptance checklist)

- [ ] Mở một video từ đường dẫn có dấu tiếng Việt và khoảng trắng.
- [ ] Mở thư mục có nhiều video, đổi video không crash.
- [ ] Player hiển thị vị trí/thời lượng đúng định dạng `HH:MM:SS.mmm`.
- [ ] Đặt/sửa IN/OUT, báo lỗi khi IN ≥ OUT hoặc vượt thời lượng.
- [ ] Chọn `positive`, `hard_negative`, `normal`, `uncertain` và lưu ghi chú.
- [ ] Xuất Fast Cut thành công, cảnh báo giới hạn keyframe khi phù hợp.
- [ ] Xuất Precise Cut thành công trên fixture tương thích.
- [ ] Cắt nhiều clip từ một video, không ghi đè clip cũ.
- [ ] UI không treo khi FFmpeg đang chạy.
- [ ] Video gốc còn nguyên (đường dẫn, size và hash với fixture kiểm thử).
- [ ] Mọi clip xuất xong có bản ghi SQLite và thông tin nguồn/timestamp.
- [ ] Export lỗi không để lại trạng thái completed hoặc file tạm bị hiểu là clip hợp lệ.
- [ ] Mở lại ứng dụng giữ được danh sách video/clip và thư mục xuất.
- [ ] CSV hiển thị đúng tiếng Việt trong Excel.
- [ ] Có hướng dẫn chạy, lỗi thường gặp và các giới hạn thời gian cắt.

### Tự động kiểm thử tối thiểu

1. Parser/formatter timestamp (0, 1 ms, >1 giờ, giá trị không hợp lệ).
2. Validation IN/OUT/padding và phạm vi video.
3. Database migration và CRUD, unique path, reopen persistence.
4. Tạo FFmpeg argument list đúng và an toàn với path có ký tự đặc biệt.
5. Export kiểm tra trạng thái lỗi/đủ điều kiện success.
6. Integration/smoke test với **video ngắn tự sinh bằng FFmpeg**, không sử dụng video của người dùng.

## 12. Các lưu ý kỹ thuật quan trọng

- Không dùng OpenCV `VideoCapture` để phát video chính nếu Qt Multimedia hoạt động tốt; OpenCV có thể dùng ở V2 để trích frame. Đừng xử lý video toàn bộ bằng Python theo từng frame chỉ để cắt clip.
- `QMediaPlayer.position()` là thời gian báo bởi backend; slider seek có thể không chính xác theo từng frame, đặc biệt video có variable frame rate.
- FPS dùng để hiển thị thông tin, **không lấy `frame_index = time * fps` làm ground truth** cho mọi video.
- Có thể có video variable frame rate, thời gian bắt đầu âm/khác 0, rotation metadata, thiếu audio; không làm hỏng quy trình vì các trường hợp này.
- Khi tạo FFmpeg command dùng danh sách arguments, tuyệt đối không nối chuỗi `shell=True` với đường dẫn người dùng.
- Cần chuẩn hóa các trường hợp trùng tên, sai quyền truy cập và đĩa đầy.
- Hiển thị trạng thái `missing source` khi file gốc bị chuyển chỗ; không tự động xóa lịch sử.
- Không chỉ dựa vào `returncode == 0`: luôn kiểm tra file đích bằng FFprobe.
- Thiết kế service và storage tách khỏi UI để sau này thay backend player, thêm frame extraction/annotation mà không làm lại toàn bộ.

## 13. Hướng dẫn cài đặt/chạy mong muốn

Codex phải viết `README.md` với các bước chính xác tương ứng dependencies thực tế trong `pyproject.toml`, ví dụ:

```bash
# Ubuntu: cần có ffmpeg, ffprobe, và các thư viện hệ thống Qt Multimedia tương ứng
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m video_dataset_tool
pytest
```

```powershell
# Windows: cài FFmpeg/FFprobe và thêm vào PATH
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m video_dataset_tool
pytest
```

Không khẳng định các lệnh chạy thành công nếu chưa thực hiện kiểm thử trong môi trường hiện có.

## 14. Hướng mở rộng sau V1 (chỉ chuẩn bị kiến trúc)

- **V2 — Frame Extraction & Selection:** chọn frame đại diện, xuất ảnh, lưu quan hệ frame–clip–video; gợi ý ảnh mờ/trùng, phân tích độ bao phủ dữ liệu.
- **V3 — Annotation Assistant:** nhãn ở cấp tình huống, vùng nghi vấn, semantic/road extent masks; hỗ trợ xuất/nhập CVAT; kiểm định consistency.
- **V4 — AI Assistance:** chạy PIDNet-S hoặc model khác để gợi ý vùng cần xem xét, không tự động thay thế nhãn được xác minh; thống kê false positives/hard negatives.

**Không triển khai V2–V4 ngay.** Chỉ cần API/service/data model có thể mở rộng về sau.

## 15. Quy tắc giao việc và báo cáo của Codex

1. Trước khi code, kiểm tra repo và mô tả ngắn phương án phù hợp với những gì đang có; không phá bỏ mã người dùng nếu đã tồn tại.
2. Thực hiện lần lượt M1 → M2 → M3 → M4; ưu tiên sản phẩm chạy được, không tạo mock UI rỗng.
3. Chạy tests, lint/type checks nếu thiết lập; sửa các lỗi thực tế phát hiện được.
4. Chỉ tạo và dùng dữ liệu thử tổng hợp. Không di chuyển/sửa/xóa video gốc người dùng.
5. Cuối cùng báo cáo: file đã tạo/sửa, cách chạy, chức năng đã hoàn thiện, test nào đã chạy và kết quả, những giới hạn còn tồn tại, OS nào đã kiểm chứng.
6. Nếu có khác biệt giữa đặc tả và giới hạn thực tế của media backend, ưu tiên hành vi an toàn, hiển thị giới hạn rõ ràng và ghi lại quyết định kỹ thuật trong `docs/ARCHITECTURE.md`.

---

## Lệnh giao việc gợi ý cho Codex

> Đọc `CODEX_VIDEO_DATASET_TOOL_V1.md` ở thư mục gốc. Hãy triển khai ứng dụng desktop Video Dataset Tool V1 đầy đủ theo tài liệu này. Thực hiện tuần tự M1–M4, chạy kiểm thử với video mẫu tự sinh, sửa lỗi, và cập nhật README + docs. Không xây chức năng AI hoặc gán nhãn nâng cao ngoài V1. Không chỉnh sửa hay di chuyển video gốc. Cuối cùng báo cáo kết quả thực tế, các lệnh chạy và giới hạn chưa giải quyết.
