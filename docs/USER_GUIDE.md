# Hướng dẫn sử dụng V1

## Bắt đầu

Chạy ứng dụng theo README từ terminal VS Code. Cửa sổ có ba vùng ngang: thư viện nguồn, trình phát, thông tin clip; lịch sử clip nằm phía dưới. Kéo vạch chia để thay đổi kích thước. Các nút xuất/xem trước/hủy luôn nằm ở cuối vùng thông tin, còn phần nhập liệu có thanh cuộn riêng.

Video nguồn được mở trực tiếp tại vị trí hiện có. Không cần đưa nguồn vào một cấu trúc dataset cố định. **Mở thư mục** thêm các video được hỗ trợ ở ngay trong thư mục đã chọn; không duyệt đệ quy. Thư viện thêm dồn, không tạo lại bản ghi khi mở cùng đường dẫn canonical.

## Xem và chọn khoảng

- Bấm video để mở phát. Bên trái hiển thị thời lượng, kích thước mã hóa, FPS và codec; không có audio là trường hợp được hỗ trợ.
- Kéo thanh thời gian rồi thả để yêu cầu tua. Đồng hồ phản ánh vị trí backend xác nhận; không suy ra frame chính xác từ FPS.
- `Phát / Dừng`, ±1s, tốc độ 0.25×–2×, âm lượng và tắt tiếng ở dưới trình phát. Khả năng thực tế phụ thuộc backend/codec.
- Hai nút `≈1 frame` tạm dừng rồi yêu cầu tua một khoảng tính từ FPS; chỉ xấp xỉ, đặc biệt với VFR.
- Bấm **Đặt IN**, **Đặt OUT** hoặc nhập thời gian với ba chữ số mili giây. Ví dụ `00:01:10.200` đến `00:01:28.500` dài 18.300 giây.
- Phải có `0 ≤ IN < OUT ≤ thời lượng nguồn`. Ô thời gian sai sẽ có cảnh báo; tác vụ xuất không bắt đầu.
- Đệm trước/sau mặc định 0, có thể chọn 3–5 giây mỗi bên. Đệm được giới hạn tại 0 và cuối video, không kéo dài vượt nguồn.
- Vạch IN/OUT và dải xanh trên timeline thể hiện khoảng **xuất sau khi cộng đệm**. Đồng hồ độ dài dự kiến cũng dùng khoảng này.
- **Xem trước khoảng xuất** phát từ đầu khoảng đến OUT rồi tạm dừng. Backend có thể dừng muộn một nhịp cập nhật vị trí; đây không phải trình kiểm định frame.

## Thông tin tình huống

| Nhóm | Sử dụng |
|---|---|
| Có tình huống nghi lấn chiếm (`positive`) | Có đối tượng/khu vực cần kiểm tra; chưa kết luận vi phạm. |
| Dễ nhận nhầm (`hard_negative`) | Trông giống nghi vấn nhưng được xác định không thuộc nhóm theo quy tắc nội bộ. |
| Giao thông bình thường (`normal`) | Không ghi nhận nghi vấn trong đoạn chọn. |
| Chưa đủ thông tin (`uncertain`) | Che khuất, thiếu căn cứ hoặc ranh giới không rõ. |

Loại vật là văn bản tùy chọn, ví dụ hàng hóa, vật liệu, cây xanh, xe dừng. Ghi chú và trạng thái xem xét không thực hiện gán nhãn AI.

**Sự kiện bắt đầu/kết thúc** để trống theo mặc định. Nếu nhập, cần cả hai thời điểm tính trên **timeline nguồn**, nằm trong khoảng clip xuất. Đây là khoảng xuất hiện tình huống, được lưu độc lập với IN/OUT/padding. Ví dụ IN=10s, OUT=20s, đệm 3s mỗi bên → clip yêu cầu 7s–23s; sự kiện 12s–18s vẫn giữ nguyên 12s–18s.

Ứng dụng giữ một bản nháp cho mỗi nguồn. Đổi video rồi quay lại sẽ khôi phục ghi chú/IN/OUT/nhóm; xuất clip không xóa bản nháp. Chỉnh thông tin sau khi đã xuất chỉ đổi bản nháp cho lần xuất tiếp theo, không sửa metadata của clip cũ.

## Xuất và kiểm tra clip

Chọn **Thư mục xuất** có quyền ghi và đủ dung lượng. Clip được đặt vào `positive`, `hard_negative`, `normal` hoặc `uncertain` dưới thư mục này.

**Fast** sao chép luồng sang MKV để giữ bitstream, có thể lệch điểm cắt vì keyframe. **Precise** mã hóa H.264/AAC sang MP4 và không crop/resize; có thể chậm và không giữ bitstream gốc. Phải xem lại clip thực tế, đặc biệt khi dùng Fast hoặc cần ranh giới rất sát.

Bấm **Xuất clip** hoặc Ctrl+E. Metadata được lưu trước, có progress; nút xuất bị khóa đến khi worker kết thúc. Vẫn có thể xem hoặc đổi video và chỉnh bản nháp khác; tác vụ đang chạy giữ snapshot của thông tin tại lúc bấm xuất.

**Hủy tác vụ xuất** dừng FFmpeg, xóa file tạm do ứng dụng sở hữu và lưu trạng thái `cancelled`. Nếu hủy trong bước FFprobe kiểm tra sau export, có thể phải chờ probe kết thúc (timeout tối đa 45 giây). Không dùng đóng cưỡng bức như một cách hủy thông thường.

Trong khi đọc metadata hoặc xuất, đóng cửa sổ sẽ được từ chối kèm thông báo chờ/hủy. Sau khi tác vụ kết thúc, đóng lại để lưu phiên. Nếu mất điện/đóng cưỡng bức, tác vụ pending/processing được chuyển thành failed khi mở lại; clip đã công bố và file tạm còn sót được giữ để tránh xóa nhầm. Có thể kiểm tra thủ công file `.vdt-<UUID>-*.partial.*` trong thư mục xuất khi ứng dụng đã đóng.

## Lịch sử và CSV

Lịch sử có đủ trạng thái chờ, đang xuất, hoàn tất, thất bại và đã hủy. Có thể kết hợp bộ lọc nguồn/nhóm/trạng thái với tìm kiếm; tìm kiếm tiếng Việt cần đúng dấu và SQLite không hỗ trợ đầy đủ đổi hoa/thường Unicode.

Chọn một dòng rồi **Chi tiết** (hoặc nhấp đúp) để xem UUID, đường dẫn, khoảng sự kiện, thời lượng thực đo và lỗi. **Mở thư mục chứa clip** dùng trình quản lý file của hệ điều hành. Không có chức năng xóa clip/video trong V1.

**Xuất CSV (toàn bộ lịch sử)** không bị giới hạn bởi các bộ lọc đang xem. CSV có BOM UTF-8 để Excel nhận tiếng Việt, khoảng thời gian giữ dạng số nguyên mili giây. Chưa kiểm tra thao tác mở file CSV trong Microsoft Excel; đã kiểm tra BOM và đọc lại nội dung bằng Python.

## Phiên làm việc và dữ liệu thất lạc

Thiết lập mặc định ảnh hưởng video chưa có bản nháp; không ghi đè bản nháp đang có. Khởi động với `--data-dir` khác để dùng một dataset độc lập. Chỉ mở một cửa sổ trên mỗi dataset để tránh phục hồi nhầm tác vụ đang chạy.

**Kiểm tra nguồn** đánh dấu mất nguồn/đã thay đổi. Nếu file bị di chuyển, ứng dụng giữ lịch sử, không tự tìm hoặc di chuyển file. Nếu file tại cùng đường dẫn đã bị thay nội dung, thông số mới chỉ được cập nhật sau khi mở lại; mỗi clip vẫn giữ size/mtime snapshot của nguồn lúc xuất.

Sao lưu: đóng ứng dụng, sao chép cả thư mục dữ liệu ứng dụng và thư mục clip. CSV không thay thế SQLite. Log chứa thông tin kỹ thuật và có thể chứa đường dẫn cục bộ; chỉ chia sẻ sau khi đã xem nội dung.
