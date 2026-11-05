# Hiệu năng và trải nghiệm sử dụng

Kiểm chứng ngày 05/11/2026 trên Windows 11, Python 3.12.10, PySide6 6.10.3, FFmpeg trong `.tools`. Các số liệu dưới đây là kết quả cục bộ trên máy hiện tại; không phải cam kết cho mọi máy, codec hoặc ổ đĩa. Ubuntu chưa được kiểm chứng.

## Những thay đổi đã triển khai

- Precise dùng H.264 **veryfast, CRF 18** mặc định; có thể chọn `fast` hoặc `medium` từ CLI và giao diện. Giữ khoảng cắt, kích thước hình và các bước kiểm tra output; không crop/resize hoặc ép FPS.
- Lịch sử dùng QTableView/model và SQL **200 clip/trang**, thay việc tạo widget item cho toàn bộ thư viện. Tìm kiếm chờ 250 ms sau khi ngừng gõ; Enter tìm ngay. Bộ lọc đổi ngay và trở về trang đầu. Làm mới giữ clip đang chọn nếu còn trong trang.
- Đăng ký nhiều nguồn trong một transaction, tra cứu theo lô. Quét thư mục dùng `scandir`.
- GUI tái dùng metadata nếu size/mtime nguồn vẫn khớp và metadata đầy đủ. **Kiểm tra nguồn** buộc đọc lại FFprobe. CLI và bước kiểm tra clip sau export vẫn probe mới.
- Không ghi draft/setting giống hệt; cache draft chỉ cập nhật sau commit thành công. Giữ SQLite WAL và `synchronous=FULL`.
- Nút xuất/xem trước khóa khi chưa có nguồn hoặc khoảng cắt sai. Thanh trạng thái có thời gian chạy và thời gian còn lại ước tính; hủy có trạng thái đang dọn file tạm. Progress chỉ phát khi phần trăm tăng.
- Schema 1→2 giữ lịch sử cũ, thêm `encoding_preset` và index sắp xếp. Các bản ghi cũ nhận `medium`, tác vụ mới lưu preset tường minh. CSV có thêm cột preset và vẫn xuất toàn bộ lịch sử.

## Đo lịch sử và lưu trữ

Lịch sử tổng hợp gồm **10.000 clip, 500 nguồn**, không dùng dữ liệu người dùng. So sánh giao diện cũ từ HEAD với giao diện mới trên cùng database và repository hiện tại, đo tuần tự để tránh tranh chấp CPU. Cả hai dùng cùng index mới; số liệu chủ yếu phản ánh cải tiến bảng và xử lý tìm kiếm. Nguồn kiểm thử là đường dẫn giả không có file; thời gian đăng ký không bao gồm giải mã/probe 500 video.

| Thao tác | Trước | Sau |
|---|---:|---:|
| Khởi tạo bảng lịch sử | 0,631 s | 0,359 s |
| Tiếp nhận 7 lần nhập từ khóa liên tiếp | 2,716 s | 0,00045 s |
| Có kết quả sau cả chuỗi nhập, gồm debounce | 2,717 s | 0,272 s |
| Số clip nạp vào bảng | 10.000 | 200 |
| Đăng ký 500 nguồn, lần đo storage riêng | 0,574 s | 0,136 s |
| Transaction khi đăng ký 500 nguồn | 500 | 1 |
| Số dòng thay đổi khi lưu cùng draft 100 lần | 100 | 1 |

Ở thời điểm chưa lưu lần nào, lần lưu draft đầu vẫn ghi một dòng. Giảm số lần ghi lặp là mục tiêu; benchmark nhỏ này không cho thấy tăng tốc đáng kể ở riêng thao tác lưu draft. Autosave tại MainWindow còn bỏ qua lời gọi repository khi toàn bộ draft/vị trí không đổi.

Phép đo tìm kiếm gõ liền một chuỗi, không mô phỏng khoảng nghỉ của người dùng. Không dùng số đo sơ bộ chạy cùng encoder để so sánh cuối cùng. Kết quả thô cục bộ: `test-artifacts/performance-2026-11-05/gui-controlled-comparison.json` và `storage-controlled-comparison.json`.

## Cắt Video_000 thực tế

Nguồn người dùng cho phép thử: HEVC/AAC, 1920×1080, 114,455 giây. Cắt **10,250 → 20,750 giây**, giữ H.264 CRF 18/AAC. Hai lượt đo đảo thứ tự preset, không chạy đồng thời benchmark CPU khác. Thời gian bao gồm export service và FFprobe kiểm tra output, chưa bao gồm mở GUI hay probe nguồn ban đầu.

| Preset | Lượt 1 | Lượt 2 | Kích thước clip | Thời lượng đo |
|---|---:|---:|---:|---:|
| medium | 15,602 s | 12,037 s | 29.858.559 byte | 10.500 ms |
| veryfast | 3,750 s | 3,750 s | 28.649.290 byte | 10.500 ms |

Trong các lượt này, veryfast giảm khoảng **69–76% thời gian chờ**. Kết quả phụ thuộc nội dung và phần cứng; preset tên fast không bảo đảm nhanh hơn medium trên mọi nguồn.

Cả bốn clip đều được FFmpeg giải mã hết video/audio với `-xerror`, không lỗi. SHA-256, size và mtime nguồn không đổi. Tên clip vẫn giữ `Video_000`, khoảng cắt và UUID.

Kiểm tra nhanh frame đầu: giải mã RGB cùng kích thước, đối chiếu frame đầu clip với frame FFmpeg đọc tại IN trên nguồn. MAE trung bình trên thang 0–255: **medium 1,3044**, **veryfast 1,4082**, giống nhau ở hai lượt tương ứng. Đây chỉ là kiểm tra đầu ra/frame đầu, **không phải đánh giá chất lượng toàn video hoặc chứng nhận chính xác từng frame**. Preset thay đổi thuật toán mã hóa; cùng CRF không có nghĩa chất lượng/bitstream giống hệt. Có thể chọn `--preset medium` khi cần giữ cấu hình cũ.

Kết quả thô và bốn clip ở thư mục chạy riêng bên dưới `test-artifacts/performance-2026-11-05/optimized/`; chúng bị Git ignore. Không đưa video người dùng vào fixture hoặc repo.

Lượt xác minh lệnh CLI đầy đủ (gồm khởi động Python, probe nguồn và SQLite) mất **5,417 giây**, xuất thêm một clip 10.500 ms vào `exports/Video_000`, dùng preset mặc định veryfast. Đã giải mã hết clip này và xác nhận nguồn nguyên hash/size/mtime. Kết quả ở `test-artifacts/performance-2026-11-05/cli-final.json`. Vì phạm vi đo khác nhau, không so trực tiếp 5,417 giây CLI với số đo riêng export service ở bảng trên.

## Cách sử dụng và tự đo

Lệnh cắt mặc định đã dùng cấu hình ưu tiên tốc độ:

```powershell
.\.venv\Scripts\python.exe -m video_dataset_tool cut --input ".\video\Video_000.mp4" --start 10.250 --end 20.750 --output-dir ".\exports\Video_000"
```

Thêm `--preset medium` để dùng preset cũ. Nếu cần giữ bitstream và chấp nhận lệch keyframe, dùng `--mode fast` (MKV, không mã hóa lại). Preset chỉ áp dụng Precise. Trong GUI, chọn Precise rồi chọn **Tốc độ mã hóa**; giá trị được lưu theo bản nháp nguồn.

Chạy benchmark thư viện tổng hợp; cần môi trường Qt có thể khởi tạo GUI:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_performance.py
```

Thêm video để đo cắt và kiểm tra decode/frame đầu. Đây là tác vụ chủ động sinh bốn clip thử và giữ lại để kiểm tra:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_performance.py --input ".\video\Video_000.mp4" --start-ms 10250 --end-ms 20750 --output-dir ".\test-artifacts\performance"
```

Mỗi lần tạo một thư mục UUID riêng với database tổng hợp, clip và `report.json`; không ghi đè kết quả trước hoặc thay đổi video nguồn. Script đo phiên bản hiện tại; bảng trước/sau ở trên dùng thêm phép đo đối chứng riêng.

## Giới hạn còn lại

Tìm kiếm substring LIKE và COUNT vẫn quét dữ liệu phù hợp; OFFSET ở trang sâu cũng có chi phí. Đã đo 10.000 clip, chưa xác minh thư viện hàng trăm nghìn clip, ổ mạng, video 4K nhiều giờ hoặc nhiều máy. Query lịch sử, quét thư mục và xuất CSV vẫn chạy trên GUI thread; CSV rất lớn có thể gây chờ. Metadata cache dựa size/mtime nên không phát hiện thay nội dung mà vẫn giữ cả hai giá trị. Thời gian còn lại chỉ là ước tính; kiểm tra cuối hoặc hủy trong FFprobe có thể cần chờ thêm.

Không thêm GPU encoder, queue hàng loạt, AI hoặc gán nhãn nâng cao. Fast vẫn approximate; Precise không tự bảo đảm frame-accurate. Sau nâng schema 2, dùng phiên bản hiện tại để mở database; phiên bản cũ hỗ trợ schema 1 sẽ từ chối mở.
