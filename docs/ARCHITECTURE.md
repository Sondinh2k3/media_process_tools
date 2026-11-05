# Kiến trúc và quyết định kỹ thuật

## Phân lớp

`app.py` khởi động QApplication, thiết lập font/style, logging xoay vòng và xử lý lỗi giao diện. `__main__.py` cung cấp `python -m video_dataset_tool`. Không có web server hoặc dependency OpenCV.

| Thư mục | Trách nhiệm |
|---|---|
| `core` | Dataclass bất biến, thời gian mili giây, kiểm tra dữ liệu, canonical path và tìm executable. |
| `ui` | Main window, QMediaPlayer/QVideoWidget, editor, timeline có IN/OUT và bảng clip. |
| `services` | FFprobe JSON, tạo danh sách argument FFmpeg, xuất/kiểm tra/công bố clip. Không phụ thuộc Qt. |
| `storage` | SQLite, migration user_version=1, repository cho nguồn/clip/thiết lập/bản nháp, CSV. |
| `workers` | QThread cho probe và export. Mỗi worker export có kết nối SQLite riêng. |
| `tests`, `scripts` | Unit/integration/Qt tests và desktop smoke với dữ liệu tự sinh. |

## Luồng mở video

Đường dẫn được resolve và normcase (Windows) để chống đăng ký trùng. UUID dùng làm khóa chính. Danh sách nguồn được lưu ngay cả khi một file chưa được probe hoặc không mở được.

Probe chạy nền, timeout 45 giây. Chỉ một probe hoạt động; thao tác chọn nhanh giữ yêu cầu mới nhất. Kết quả có generation token để thông số của video cũ không thay thế video mới. Chỉ metadata có thời lượng dương và video stream mới được chấp nhận. FPS lưu phân số numerator/denominator từ `avg_frame_rate`; không coi đó là số frame thực của VFR.

Qt phụ trách giải mã/hiển thị/seek/audio. Clock dùng `positionChanged`, không tự giả lập vị trí seek. Slider chỉ yêu cầu seek khi thả. Khi đổi/đóng nguồn, dùng `setSource(QUrl())` để ngừng I/O và giải phóng nguồn theo [hợp đồng QMediaPlayer](https://doc.qt.io/qt-6.10/qmediaplayer.html#source-prop); đóng cửa sổ còn ngắt video/audio output. Không gọi stop dư thừa trước setSource: kiểm thử từng tái hiện deadlock ở stop ngay sau seek trong trạng thái pause. Probe/export chưa kết thúc thì cửa sổ chưa cho đóng.

Kết quả worker vào các method `@Slot` của MainWindow qua QueuedConnection, callback media cũng khai báo Slot. Giao diện và kết nối SQLite chính chỉ được thao tác ở GUI thread theo [hướng dẫn signal/slot Qt for Python](https://doc.qt.io/qtforpython-6.10/tutorials/basictutorial/signals_and_slots.html). V1 pin PySide6 6.10.3 để tái lập cấu hình đã kiểm chứng; không khẳng định mọi bản Qt mới hơn có cùng hành vi.

## Luồng export và an toàn nguồn

1. Kiểm tra timecode, IN/OUT, padding, nhóm, review status và khoảng sự kiện. Tạo UUID mới, snapshot metadata/size/mtime lấy từ lần mở nguồn thành công.
2. Lưu draft và bản ghi `pending` trong SQLite trước khi worker bắt đầu. Worker cập nhật `processing` bằng một kết nối riêng.
3. Kiểm tra lại source stat so với snapshot, executable, thư mục và ước lượng dung lượng. Không tính full hash các video lớn; hash chỉ dùng cho dữ liệu tổng hợp trong test.
4. Tạo file tạm ngẫu nhiên thuộc ứng dụng trong thư mục đích. `-y` chỉ áp dụng file tạm riêng này; không áp dụng nguồn hoặc clip cũ. `subprocess` dùng list argument, không dùng shell.
5. Chạy FFmpeg; đọc progress trên pipe riêng, stderr vào temporary file để tránh đầy pipe/bộ nhớ. Worker kiểm tra cancel mỗi 100 ms; nếu không có báo cáo tiến độ trong 180 giây thì dừng. Terminate → wait tối đa 5 giây → kill nếu cần.
6. Exit 0 chưa đủ: kiểm tra file ≥128 byte, FFprobe đọc được video và độ dài phù hợp dung sai. Không tuyên bố đầu clip đúng frame chỉ vì độ dài đúng.
7. Dành tên đích bằng tạo file độc quyền (`xb`), rồi `os.replace` file tạm vào tên UUID đã dành. Nếu tên đã tồn tại thì lỗi, không ghi đè clip cũ. Dọn file tạm/file dành tên do chính job tạo khi lỗi/hủy.
8. Lưu terminal state trước khi gửi kết quả lên UI. Nếu ghi SQLite lỗi sau khi clip đã tạo, giữ file và báo lỗi lưu metadata, không nhận là tác vụ thành công.

Filesystem và SQLite không có transaction chung. Nếu tiến trình chết đúng sau công bố file nhưng trước commit metadata, clip có thể còn trên đĩa trong khi bản ghi đang processing. Khi mở lại, pending/processing được chuyển thành failed với lý do gián đoạn; không tự nhận completed, không xóa file đã công bố. File tạm còn từ hard crash không tự động xóa vì không thể xác minh quyền sở hữu chỉ bằng tên file; hướng dẫn người dùng kiểm tra khi ứng dụng đã đóng.

`QLockFile` theo thư mục dữ liệu ngăn hai phiên đồng thời và việc phục hồi nhầm job của phiên khác. SQLite bật foreign keys, WAL, synchronous FULL, timeout 10 giây, transaction cho mỗi thay đổi. Schema mới hơn phiên bản đang hỗ trợ bị từ chối, không downgrade hoặc xóa dữ liệu.

## Định dạng cắt và độ chính xác

- **Fast**: input `-ss`, `-t`, map video đầu tiên và các audio tùy chọn, `-c copy`, `-avoid_negative_ts make_zero`, MKV. MKV được chọn thay cho MP4 để giảm lỗi mux codec/audio không tương thích. Vẫn có codec đặc biệt mà Matroska không hỗ trợ; ứng dụng báo lỗi và cho người dùng chọn Precise.
- **Precise**: input-side accurate seek của FFmpeg, giải mã từ keyframe trước và loại preroll khi re-encode; H.264/libx264 preset medium CRF18, audio AAC 192k, MP4 faststart. Không `scale`, `crop` hoặc ép FPS. Không tự fallback sang codec khác khi encoder không có.
- Dùng `-noautorotate` để tránh tự thay đổi kích thước/pixel do autorotation trong FFmpeg. Display rotation phụ thuộc metadata/container/player; nguồn có rotation phức tạp chưa được kiểm chứng, cần xem lại clip thực tế.
- Dung sai Fast: `max(3000 ms, 10% khoảng yêu cầu)`. Clip với GOP dài có thể bị từ chối vì chênh nhiều; đề nghị Precise thay vì âm thầm chấp nhận.
- Dung sai Precise: `max(150 ms, 2000/FPS ms)`; không có FPS dùng 250 ms. Dung sai không thay thế kiểm định frame/event bằng mắt.
- `actual_start_ms=NULL` cho cả hai vì chưa xác minh frame đầu so với nguồn. `actual_duration_ms` lưu độ dài FFprobe đo. Fast luôn `approximate`; Precise `unknown` cho độ chính xác vị trí. Chưa tạo trường hợp `verified` một cách suy đoán.
- Timeline và preview dùng thời gian backend; nút frame chỉ xấp xỉ. Timestamp nguồn có offset khác 0 được kiểm thử với fixture. Không hứa hẹn đầy đủ cho VFR/rotation/timestamp hỏng.

## Dữ liệu và khôi phục

Nguồn có UUID, unique canonical path, size/mtime, duration, rational FPS, resolution, codec, last_seen. Clip có FK tới nguồn và snapshot đường dẫn/size/mtime để lịch sử vẫn có nghĩa khi file tại cùng đường dẫn bị thay. `availability` cập nhật khi khởi động hoặc Kiểm tra nguồn; mất file không xóa nguồn/clip.

IN/OUT sau padding là requested range; event range độc lập, mặc định NULL. Draft giữ ô IN/OUT gốc, padding, text và vị trí player. Draft autosave debounce 350 ms, định kỳ 2 giây, trước đổi nguồn/xuất/đóng. SQLite giữ bản nháp và thiết lập để `--data-dir` tạo dataset tự chứa; không dùng CSV làm database.

CSV UTF-8-SIG được ghi vào file tạm rồi replace. Cấm xuất CSV vào đường dẫn nguồn, clip hoặc database đã đăng ký. CSV gồm toàn bộ lịch sử, không bị bộ lọc UI giới hạn.

## Phạm vi và giới hạn

Chỉ source-run, chưa có installer/PyInstaller. Windows đã chạy thử; Ubuntu chưa xác minh. Backend Qt có thể không hỗ trợ một số codec dù FFprobe đọc được; có thông báo ngay trong vùng player. Precise cần FFmpeg có libx264/AAC. Ước lượng dung lượng chỉ là phát hiện sớm, lỗi ghi thực tế vẫn được xử lý.

Thư viện danh sách Qt Widgets phù hợp quy mô V1; chưa phân trang database hoặc tối ưu thư viện hàng trăm nghìn clip. Search SQLite LIKE chưa đầy đủ Unicode case folding. Không xóa nguồn/clip, relink nguồn, batch queue, AI, frame extraction hoặc annotation. Các service/storage tách khỏi UI để có thể mở rộng sau này mà không thêm tính năng ngoài V1.
