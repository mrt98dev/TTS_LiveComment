# cmt-speak — Quick Controls, Content Filter & Auto-Reconnect (Design)

## Mục tiêu

Bổ sung 3 nhóm tính năng vận hành cho MVP hiện có ([2026-09-09-cmt-speak-design.md](2026-09-09-cmt-speak-design.md)),
được người dùng chọn ưu tiên trong số các hướng "ngoài phạm vi" ban đầu:

1. **Điều khiển nhanh** khi đang đọc: bỏ qua, xóa hàng đợi.
2. **Lọc nội dung**: chặn/bíp từ cấm, chặn comment trùng lặp.
3. **Tự động reconnect** khi mất kết nối do lỗi mạng.

Không đổi kiến trúc tổng thể của MVP — cả 3 đều cắm thêm vào pipeline
Connector → Queue → TTSWorker → Audio đã có.

## Kiến trúc bổ sung

```
Connector (thêm reconnect logic)
        │
        ▼
  Shared Queue ──── clear() [nút Xóa hàng đợi]
        │
        ▼
   TTSWorker ──── skip_current() [nút Bỏ qua]
        │
        ▼
  CommentFilter (mới) — quyết định: đọc bình thường / bíp từ cấm / bỏ qua
        │
        ▼
   VieNeu-TTS → AudioOutput.stop() [ngắt audio khi Bỏ qua ở chế độ "ngắt ngay"]
```

`CommentFilter` là thành phần mới, độc lập, được `TTSWorker` gọi trước khi format
và tổng hợp giọng cho mỗi comment — tách riêng để test được mà không cần TTS thật,
theo đúng cách `template.py`/`voice_manager.py` đã tách trong MVP.

Log panel (`LogPanel`) có thêm trạng thái thứ 4 bên cạnh
chờ/đang đọc/đã đọc đã có: **🚫 đã lọc / đã xóa / đã bỏ qua** — comment bị chặn vẫn
hiển thị (không biến mất im lặng) để streamer biết filter đang hoạt động và có thể
điều chỉnh blocklist nếu lọc nhầm.

## 1. Điều khiển nhanh

### Nút "Bỏ qua"
Một nút duy nhất; hành vi cấu hình trong Settings (mặc định: ngắt ngay):

- **Ngắt đọc ngay**: `AudioOutput` có thêm `stop()` gọi `sounddevice.stop()`. Vì
  `play_stream()` hiện dùng `sd.play(..., blocking=True)`, gọi `stop()` từ thread
  khác (UI thread, khi bấm nút) sẽ làm lệnh `play_stream()` đang chặn trên
  `TTSWorker` trả về ngay lập tức, vòng lặp `_process_one()` tiếp tục sang comment
  kế tiếp trong hàng đợi như bình thường (đã có `finally: finished_reading.emit()`
  nên trạng thái log tự cập nhật đúng, không cần thêm state riêng cho "bị bỏ qua
  giữa chừng" — coi như đã đọc xong).
- **Chỉ bỏ comment kế tiếp**: không đụng audio đang phát. Lấy 1 phần tử đang chờ ở
  đầu hàng đợi (`CommentQueue`) ra, không đưa vào TTSWorker, đánh dấu log tương
  ứng "🚫 đã bỏ qua".
- Bấm khi không có gì đang phát (chế độ ngắt ngay) hoặc hàng đợi rỗng (chế độ bỏ
  kế tiếp): coi là no-op, không báo lỗi.

### Nút "Xóa hàng đợi"
- Hiện hộp xác nhận trước khi xóa (hành động không thể hoàn tác).
- `CommentQueue` thêm `clear() -> list[Comment]`: rút sạch các phần tử **đang chờ**
  (không đụng comment đang đọc dở, vì nó đã được `TTSWorker` lấy ra khỏi queue rồi),
  trả về danh sách đã xóa để UI biết chính xác dòng log nào cần đánh dấu.
- Đánh dấu tất cả dòng log tương ứng "🚫 đã xóa".
- `clear()` phải thread-safe với việc `TTSWorker` đang gọi `queue.get()` đồng thời
  (dùng lock sẵn có bên trong `queue.Queue`, không cần cơ chế khóa riêng).

## 2. Lọc nội dung

### Quản lý danh sách từ cấm (Settings — panel mới "Từ cấm")
- Danh sách trống mặc định; người dùng tự thêm/xóa từng từ/cụm từ (UI dạng list +
  nút thêm/xóa, theo đúng mẫu đã dùng cho quản lý giọng clone).
- Nút **Import** từ file `.txt` (mỗi dòng 1 từ/cụm từ, bỏ qua dòng trống).
- Nút **"Xem danh sách mẫu"**: app đóng gói sẵn 1 file `.txt` nhỏ (vài chục từ nhạy
  cảm phổ biến + vài mẫu định dạng spam link thường gặp), hiển thị trong dialog để
  người dùng chọn import toàn bộ hoặc từng dòng — không tự động áp dụng.
- So khớp: theo **từ/cụm từ nguyên vẹn** (ranh giới từ, không khớp một phần bên
  trong từ khác), không phân biệt hoa/thường, chuẩn hóa Unicode NFC trước khi so
  sánh (tránh lệch do 2 cách gõ dấu tiếng Việt khác nhau tạo ra chuỗi Unicode khác
  nhau dù nhìn giống hệt).

### Xử lý khi khớp từ cấm (cấu hình 1 trong 2 chế độ, Settings)
- **Bỏ qua toàn bộ comment**: không tổng hợp giọng, đánh dấu log "🚫 đã lọc".
- **Bíp từ cấm, đọc phần còn lại**: tách text thành các đoạn quanh (các) từ cấm
  tìm thấy; với mỗi từ cấm khớp, tổng hợp giọng cho đoạn text ngay trước nó (nếu
  không rỗng), sau đó chèn một tiếng bíp (tone sin ngắn, ~0.3s, tự sinh bằng numpy,
  không cần file audio), lặp lại tới đoạn cuối cùng. Chấp nhận ngữ điệu hơi khựng
  nhẹ ở điểm nối do mỗi đoạn được tổng hợp riêng.

### Chặn trùng lặp (cấu hình 1 trong 2 chế độ, Settings)
- **Theo nội dung**: text giống hệt nhau (sau chuẩn hóa) xuất hiện lại trong vòng
  N giây gần nhất (mặc định 10s, chỉnh được trong Settings), không phân biệt ai
  gửi — chỉ đọc lần đầu tiên trong cửa sổ đó.
- **Theo người gửi**: chỉ chặn khi chính người đó gửi lại đúng nội dung liên tiếp;
  người khác hỏi câu giống hệt vẫn được đọc bình thường.
- Comment bị chặn do trùng: đánh dấu log "🚫 đã lọc (trùng)", không đọc.
- `CommentFilter` giữ một lịch sử ngắn hạn (giới hạn theo thời gian, tự dọn các
  mục quá cửa sổ N giây) để kiểm tra trùng lặp — không cần lưu toàn bộ lịch sử
  phiên live.

## 3. Tự động reconnect

Áp dụng cho cả `TikTokConnector` và `YouTubeConnector`, mỗi connector tự phân loại
lỗi của nền tảng mình:

- **Chỉ tự động thử lại** với lỗi thuộc nhóm mạng/kết nối (mất websocket, timeout,
  lỗi HTTP tạm thời...).
- **Không thử lại** (dừng hẳn, báo trạng thái rõ ràng) với lỗi nghĩa là live đã
  kết thúc thật sự: TikTok `UserOfflineError`; YouTube video không còn
  `activeLiveChatId` / không tìm thấy live chat.
- Thử lại **vô hạn**, giãn cách tăng dần: 2s → 5s → 10s → 30s, giữ nguyên 30s cho
  các lần tiếp theo.
- Trạng thái mới `RECONNECTING` (mở rộng `status_changed`) kèm thông điệp có số
  lần thử và thời gian chờ tiếp theo (vd "Mất kết nối, thử lại sau 10s (lần 3)...")
  để streamer biết app đang tự xử lý, không phải bị treo.
- Vòng lặp reconnect phải dừng ngay khi người dùng chủ động bấm "Ngắt kết nối" —
  dùng cờ dừng đã có sẵn trong mỗi connector (`stop()`), kiểm tra cờ này trước mỗi
  lần thử lại thay vì chỉ kiểm tra một lần khi bắt đầu vòng lặp.

## Testing

- `CommentFilter`: unit test khớp từ nguyên vẹn (không dính một phần trong từ
  khác), không phân biệt hoa/thường, chuẩn hóa Unicode; cả 2 chế độ xử lý từ cấm
  (bỏ qua/bíp, bao gồm trường hợp từ cấm xuất hiện nhiều lần hoặc ở đầu/cuối câu);
  cả 2 chế độ trùng lặp (theo nội dung có cửa sổ thời gian, theo người gửi); lịch
  sử trùng lặp tự dọn đúng theo cửa sổ thời gian.
- Quick controls: unit test `CommentQueue.clear()` (rút hết phần tử đang chờ,
  không đụng phần đang được worker xử lý, trả đúng danh sách đã xóa); `TTSWorker`
  skip ở cả 2 chế độ (mock `AudioOutput.stop()` được/không được gọi tùy chế độ);
  no-op khi không có gì để bỏ qua/xóa.
- Auto-reconnect: unit test logic phân loại lỗi (mạng vs live-đã-kết-thúc) cho
  từng connector bằng exception mẫu, không cần kết nối thật; hàm tính thời gian
  chờ backoff theo số lần thử (hàm thuần, test không cần sleep thật).
- Test tay: thử reconnect thật (ngắt mạng tạm thời khi đang live thật) — khó tự
  động hóa hoàn toàn, ghi rõ là bước verify thủ công cuối cùng.

## Error handling

- Bíp từ cấm xuất hiện nhiều lần/ở đầu/cuối câu: tách thành nhiều đoạn tương ứng
  vị trí khớp; đoạn rỗng (từ cấm ở đầu hoặc cuối, hoặc 2 từ cấm liền nhau) thì bỏ
  qua bước tổng hợp cho đoạn đó, chỉ phát tiếng bíp.
- "Xóa hàng đợi" phải thread-safe với `TTSWorker` đang `queue.get()` đồng thời —
  dựa vào tính thread-safe sẵn có của `queue.Queue`, không tự chế cơ chế khóa mới.
- "Bỏ qua" ở chế độ ngắt ngay khi không có audio nào đang phát, hoặc "Bỏ qua" ở
  chế độ bỏ kế tiếp khi hàng đợi rỗng: coi là no-op, không báo lỗi.
- Reconnect không được "hồi sinh" một kết nối mà người dùng đã chủ động ngắt.

## Ngoài phạm vi (out of scope cho bản thiết kế này)

- Hai nút riêng biệt cho "ngắt đọc ngay" và "bỏ kế tiếp" — gộp thành 1 nút cấu
  hình được, theo yêu cầu.
- Danh sách từ cấm mặc định đầy đủ/chuẩn hóa theo tiêu chuẩn kiểm duyệt — chỉ có
  1 file mẫu nhỏ mang tính gợi ý, người dùng tự chịu trách nhiệm mở rộng.
- Giới hạn số lần thử reconnect — chọn vô hạn theo yêu cầu, không có cấu hình đổi
  sang giới hạn số lần.
- Các hướng còn lại từ danh sách brainstorm ban đầu (Shopee Live, tự động phát
  hiện live, gán giọng theo người bình luận, lưu lịch sử log, overlay, đa
  profile...) — để các vòng thiết kế sau nếu cần.
