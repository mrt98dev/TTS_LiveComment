# Quick Controls, Content Filter & Auto-Reconnect — Implementation Plan

Dựa trên [2026-09-09-quick-controls-filter-reconnect-design.md](../specs/2026-09-09-quick-controls-filter-reconnect-design.md).
Mỗi phase làm ra một lát cắt chạy được, kiểm chứng độc lập trước khi sang phase kế.

## Song song hóa

Phase 0 (nền tảng, đụng `tts/worker.py`) phải làm **tuần tự trước**. Sau đó 3 nhánh
độc lập file có thể chạy song song:

- **Nhánh A** — Phase 1-2: Điều khiển nhanh (UI + `CommentQueue.clear()` +
  `AudioOutput.stop()` đã có khung từ Phase 0, giờ nối vào UI)
- **Nhánh B** — Phase 3-5: `CommentFilter` (blocklist, bíp, trùng lặp) + Settings UI
  quản lý blocklist
- **Nhánh C** — Phase 6-7: Auto-reconnect cho cả 2 connector

Phase 8 (ráp filter vào worker + UI cuối) làm sau khi B xong, vì nó sửa lại
`tts/worker.py` lần nữa — cần B đã có `CommentFilter` sẵn. Phase 9 rà soát cuối.

## Phase 0 — Nền tảng: mở khung cho skip/filter trong TTSWorker

- `queue_bus.py`: thêm `CommentQueue.clear() -> list[Comment]` — rút sạch phần tử
  đang chờ trong `queue.Queue` nội bộ (dùng `get_nowait()` trong vòng lặp tới khi
  `Empty`), trả về danh sách đã rút theo đúng thứ tự FIFO ban đầu.
- `audio/output.py`: thêm `AudioOutput.stop()` gọi `sounddevice.stop()`.
- `tts/worker.py`: thêm `TTSWorker.skip_current(interrupt: bool)`:
  - `interrupt=True`: gọi `self._audio.stop()`.
  - `interrupt=False`: không làm gì ở đây — việc "bỏ comment kế tiếp" thao tác
    trực tiếp trên `CommentQueue` từ UI (không cần qua worker), xem Phase 1.
  - Đảm bảo gọi khi không có gì đang phát là no-op an toàn (không lỗi).
- **Test**: `tests/test_queue_bus.py` thêm case cho `clear()` (rút đúng thứ tự,
  không đụng phần tử đã bị `get()` trước đó, hàng đợi rỗng thì trả `[]`).
- **Kiểm chứng**: `pytest tests/test_queue_bus.py` pass; gọi `AudioOutput.stop()`
  thủ công trong lúc `play_stream()` đang chặn ở thread khác → xác nhận `play_stream`
  trả về ngay (test tay với audio thật, tương tự các smoke test trước).

## Nhánh A — Phase 1-2: Điều khiển nhanh

### Phase 1 — Setting hành vi "Bỏ qua" + nút UI
- `config.py`: thêm key `skip_mode` (`"interrupt"` | `"next_only"`, mặc định
  `"interrupt"`).
- `ui/settings_panel.py`: thêm dropdown/radio chọn hành vi nút Bỏ qua, lưu qua nút
  "Lưu cài đặt" đã có (theo đúng cơ chế Save hiện tại).
- `ui/main_window.py`: thêm nút "Bỏ qua" cạnh nút Tạm dừng. Khi bấm:
  - đọc `cfg.get("skip_mode")`.
  - `interrupt`: gọi `worker.skip_current(interrupt=True)`.
  - `next_only`: gọi `queue.get_nowait()`-kiểu (thêm `CommentQueue.pop_next() ->
    Optional[Comment]` rút đúng 1 phần tử đầu, không lỗi nếu rỗng) rồi báo
    `LogPanel` đánh dấu "🚫 đã bỏ qua" cho đúng dòng.
- **Test**: unit test `skip_mode` mặc định đúng trong `Config`; test
  `CommentQueue.pop_next()` (rút đúng 1 phần tử đầu, trả `None` nếu rỗng, không
  đụng phần tử sau).
- **Kiểm chứng thủ công**: chạy `MockConnector`, bấm Bỏ qua ở cả 2 chế độ, xác
  nhận đúng hành vi (ngắt audio ngay / chỉ mất 1 comment chưa đọc).

### Phase 2 — Nút "Xóa hàng đợi" + trạng thái log mới
- `ui/log_panel.py`: thêm `ReadStatus.CLEARED` / `SKIPPED` (gộp chung 1 trạng thái
  "🚫" là đủ, phân biệt qua text nếu cần) và method `mark_removed(comments:
  list[Comment])` đánh dấu nhiều dòng cùng lúc mà không cần đợi tín hiệu từ
  worker (khác với luồng pending→reading→read hiện có).
- `ui/main_window.py`: nút "Xóa hàng đợi" → `QMessageBox.question` xác nhận →
  nếu đồng ý, gọi `queue.clear()`, truyền kết quả cho `log_panel.mark_removed()`.
- **Test**: `tests/test_log_panel.py` thêm case cho `mark_removed()` (đánh dấu
  đúng các item, không đụng item đang ở trạng thái READING/READ).
- **Kiểm chứng thủ công**: dồn vài comment vào hàng đợi (tạm dừng đọc để chúng
  không bị đọc hết), bấm Xóa hàng đợi, xác nhận hộp thoại hiện ra, sau khi đồng ý
  các dòng log chuyển "🚫 đã xóa" đúng, comment đang đọc dở (nếu có) không bị ảnh
  hưởng.

## Nhánh B — Phase 3-5: CommentFilter & quản lý blocklist

### Phase 3 — `CommentFilter`: blocklist chặn nguyên từ
- `tts/filter.py` (mới): hàm `normalize_text(s) -> str` (Unicode NFC + lowercase);
  class `CommentFilter` với `contains_blocked_word(text, blocklist) -> list[str]`
  (trả về (các) từ cấm khớp, khớp theo ranh giới từ bằng regex `\b`, trên bản đã
  chuẩn hóa).
- `config.py`: thêm key `blocklist` (`list[str]`, mặc định `[]`), `blocklist_mode`
  (`"skip"` | `"bleep"`, mặc định `"skip"`).
- **Test**: `tests/test_filter.py` — khớp từ nguyên vẹn (không dính một phần
  trong từ khác, vd "đmx" không khớp "đm" nếu "đm" không phải từ riêng), không
  phân biệt hoa/thường, 2 chuỗi Unicode khác nhau nhưng cùng hiển thị vẫn khớp
  sau chuẩn hóa.

### Phase 4 — Chế độ "bíp" + trùng lặp
- `tts/filter.py`: thêm `split_around_blocked_words(text, blocklist) ->
  list[tuple[str, bool]]` (danh sách đoạn kèm cờ "là từ cấm cần bíp hay đoạn text
  thường"), xử lý đúng khi từ cấm ở đầu/cuối/liền nhau (đoạn rỗng bị loại khỏi
  kết quả).
- Thêm hàm sinh tiếng bíp: `generate_beep_tone(sample_rate, duration=0.3) ->
  np.ndarray` (sin wave tần số cố định, ví dụ 1000Hz).
- `config.py`: thêm `dedup_mode` (`"content"` | `"author"`, mặc định `"content"`),
  `dedup_window_seconds` (mặc định `10`).
- `CommentFilter`: thêm `is_duplicate(comment) -> bool`, giữ lịch sử ngắn hạn
  `(author, normalized_text, ts)`, tự dọn mục cũ hơn `dedup_window_seconds` mỗi
  lần gọi.
- **Test**: bíp — tách đúng đoạn với từ cấm ở giữa/đầu/cuối/liền nhau, nối lại
  đúng thứ tự; trùng lặp — cả 2 chế độ, xác nhận mục quá cửa sổ thời gian không
  còn được tính là trùng (test bằng cách truyền `ts` giả lập, không cần sleep
  thật).

### Phase 5 — Settings UI: quản lý blocklist
- `assets/sample_blocklist.txt` (mới, vài chục dòng mẫu — từ nhạy cảm phổ biến +
  vài mẫu pattern spam link).
- `ui/settings_panel.py`: panel mới "Từ cấm" — `QListWidget` hiển thị
  `cfg.blocklist`, nút Thêm/Xóa (thao tác trực tiếp trên list + Lưu cài đặt như
  các field khác), nút "Import từ file..." (`QFileDialog` chọn `.txt`, mỗi dòng 1
  từ), nút "Xem danh sách mẫu" (dialog liệt kê `sample_blocklist.txt`, có thể tick
  chọn dòng để import vào blocklist đang chỉnh, không tự áp dụng).
- Thêm 2 dropdown cấu hình: chế độ xử lý từ cấm (skip/bleep), chế độ trùng lặp
  (content/author) + ô nhập `dedup_window_seconds`.
- **Kiểm chứng thủ công**: thêm từ cấm, import từ file mẫu, đổi chế độ, bấm Lưu,
  khởi động lại app xác nhận blocklist + cấu hình còn nguyên.

## Nhánh C — Phase 6-7: Auto-reconnect

### Phase 6 — TikTokConnector reconnect
- `connectors/base.py`: thêm status `RECONNECTING`.
- `connectors/tiktok_connector.py`: tách hàm `_is_reconnectable_error(exc) ->
  bool` (True cho lỗi mạng/kết nối; False cho `UserOfflineError` và các lỗi nghĩa
  là live đã kết thúc). Bọc `_run()` trong vòng lặp: nếu lỗi reconnectable và
  connector chưa bị `stop()`, emit `RECONNECTING` kèm thông điệp có số lần
  thử/thời gian chờ, `time.sleep` theo backoff (2s→5s→10s→30s, giữ 30s), thử kết
  nối lại; nếu không reconnectable, dừng hẳn như cũ.
- Kiểm tra cờ dừng (đặt bởi `stop()`) **trước mỗi lần thử lại**, không chỉ lúc vào
  vòng lặp.
- **Test**: `tests/test_tiktok_connector.py` thêm case cho `_is_reconnectable_error`
  (mock các loại exception, không cần kết nối thật); test backoff timing là hàm
  thuần `next_backoff_delay(attempt: int) -> float`.

### Phase 7 — YouTubeConnector reconnect
- Tương tự Phase 6: `_is_reconnectable_error` phân loại dựa trên
  `describe_http_error`/loại exception (network/HTTP tạm thời → reconnectable;
  "video không live"/"live chat không còn hoạt động" → không).
- Dùng chung hàm `next_backoff_delay` với TikTok (đặt trong `connectors/base.py`
  hoặc 1 module dùng chung nhỏ, tránh trùng lặp).
- **Test**: tương tự Phase 6, dùng fixture lỗi HTTP mẫu đã có sẵn từ MVP.

## Phase 8 — Ráp CommentFilter vào TTSWorker + UI trạng thái reconnect

- `tts/worker.py`: trong `_process_one`, trước khi gọi `_speak`, gọi
  `CommentFilter` (nhận qua constructor): nếu bị chặn theo blocklist (chế độ
  skip) hoặc trùng lặp → emit `finished_reading` ngay (không gọi `_speak`), log
  cảnh báo phù hợp để `LogPanel`/status bar phân biệt lý do. Nếu chế độ bíp và có
  từ cấm → dùng `split_around_blocked_words` + `generate_beep_tone`, tổng hợp
  từng đoạn qua `_voices.infer_stream`, nối với tiếng bíp, phát qua
  `AudioOutput.play_stream` (nối các đoạn wav thành 1 mảng numpy trước khi phát,
  theo đúng nguyên tắc "gom rồi phát 1 lần" đã áp dụng để tránh giật audio).
- `ui/log_panel.py`: phân biệt "🚫 đã lọc" (blocklist) và "🚫 đã lọc (trùng)"
  (dedup) qua tham số message khi gọi `mark_removed`/tương đương.
- `ui/connection_panel.py`: hiển thị trạng thái `RECONNECTING` kèm thông điệp
  (đã có cơ chế `_on_status_changed` nhận `(status, message)`, chỉ cần thêm dòng
  ánh xạ nhãn hiển thị, không coi là trạng thái "kết thúc" như DISCONNECTED/ERROR
  — input vẫn khóa, nút vẫn hiện "Ngắt kết nối" trong lúc đang tự thử lại).
- **Kiểm chứng thủ công**: `MockConnector` không cần đổi, nhưng viết 1 script test
  tay thêm sẵn từ cấm rồi bơm comment chứa từ đó qua `queue.put()` trực tiếp, xác
  nhận bị lọc/bíp đúng; test tay riêng cho reconnect như spec đã ghi (ngắt mạng
  tạm thời khi đang live thật).

## Phase 9 — Rà soát cuối

- Chạy toàn bộ `pytest`, đảm bảo pass.
- Đối chiếu lại mục "Ngoài phạm vi" trong design doc: xác nhận chỉ 1 nút Bỏ qua
  (không phải 2), không có giới hạn số lần reconnect, blocklist mặc định trống.
- Test tay tổng hợp: một phiên live thật (TikTok hoặc YouTube) chạy đủ lâu để trải
  qua ít nhất 1 lần mất kết nối thật (hoặc giả lập bằng cách tắt wifi vài giây),
  xác nhận tự kết nối lại đúng; trong lúc đó thử cả nút Bỏ qua và Xóa hàng đợi khi
  có backlog thật.
