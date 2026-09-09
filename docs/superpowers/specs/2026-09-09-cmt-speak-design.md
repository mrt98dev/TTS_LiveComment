# cmt-speak — Live Comment Reader (Design)

## Mục tiêu

Ứng dụng desktop (Windows/macOS) đọc to bình luận từ phiên live TikTok và YouTube bằng
giọng nói tiếng Việt tổng hợp cục bộ (VieNeu-TTS), giúp streamer nghe/phản hồi bình luận
mà không cần liên tục nhìn màn hình chat. Shopee Live nằm ngoài phạm vi MVP này (không có
API public, để lại cho giai đoạn sau).

## Kiến trúc tổng quan

```
┌──────────────────┐     ┌───────────────────┐
│ TikTok Connector  │     │ YouTube Connector  │
│ (TikTokLive lib)  │     │ (Data API polling) │
└─────────┬─────────┘     └─────────┬──────────┘
          │    normalize → Comment   │
          └────────────┬─────────────┘
                        ▼
                ┌───────────────┐
                │  Shared Queue  │  (FIFO, thread-safe)
                └───────┬────────┘
                        ▼
                ┌───────────────┐
                │  TTS Worker    │──▶ VieNeu-TTS engine ──▶ audio output device
                │  (1 thread)    │
                └───────┬────────┘
                        ▼
                ┌───────────────┐
                │  PySide6 UI    │  (log realtime, controls, settings)
                └───────────────┘
```

Cả hai connector chạy độc lập, có thể bật/tắt riêng biệt, cùng đẩy comment đã chuẩn hóa vào
một hàng đợi chung theo đúng thứ tự đến. Một worker duy nhất tiêu thụ hàng đợi tuần tự,
tổng hợp câu theo template, gọi TTS, phát audio. UI chỉ hiển thị và điều khiển, không xử lý
logic nghiệp vụ.

## Tech stack

- **Ngôn ngữ/Framework UI**: Python + PySide6 (Qt) — dùng chung ngôn ngữ với TTS engine và
  connector, tránh giao tiếp liên-tiến-trình, đơn giản hóa đóng gói.
- **TTS**: [VieNeu-TTS](../../../../tts-local/VieNeu-TTS) (SDK `vieneu`, mode v3 Turbo mặc
  định, chạy CPU/ONNX torch-free hoặc GPU nếu có).
- **TikTok ingestion**: thư viện `TikTokLive` (Python, kết nối webcast không chính thức của
  TikTok qua asyncio).
- **YouTube ingestion**: YouTube Data API v3 (`liveChatMessages.list`), cần người dùng tự
  cấp API key riêng.
- **Audio playback**: `sounddevice` để liệt kê và phát ra thiết bị output tùy chọn (hỗ trợ
  route qua virtual audio cable vào OBS).
- **Đóng gói**: PyInstaller, build riêng trên Windows và macOS (không cross-compile).

## Các thành phần

### 1. TikTok Connector
- Kết nối bằng username TikTok nhập thủ công.
- Lắng nghe event comment qua `TikTokLive`, chuẩn hóa thành `Comment(platform="tiktok",
  author, text, ts)`.
- Mất kết nối / live kết thúc → cập nhật trạng thái "Disconnected" lên UI. Không tự động
  reconnect ở MVP; người dùng bấm Connect lại thủ công.

### 2. YouTube Connector
- Kết nối bằng URL/video ID live nhập thủ công + API key (nhập và lưu trong Settings).
- Polling `liveChatMessages.list` theo `pollingIntervalMillis` mà API trả về để không vượt
  quota (mặc định 10.000 unit/ngày, mỗi lần gọi tốn 5 unit).
- Lỗi rõ ràng ngay trong panel kết nối khi: video không phải live, live chưa bắt đầu, API
  key sai, hoặc hết quota.

### 3. Shared Queue
- `queue.Queue` thread-safe, nhận comment từ cả hai connector (chạy trong một event loop
  asyncio ở thread nền), giữ nguyên thứ tự đến.
- MVP không giới hạn độ dài hàng đợi và không drop bất kỳ comment nào — đọc tuần tự tất cả.
  Số lượng đang chờ được hiển thị trên UI để streamer biết độ trễ hiện tại.
- Một connector rớt kết nối không ảnh hưởng connector còn lại hay hàng đợi chung.

### 4. TTS Worker
- 1 thread riêng, vòng lặp: lấy `Comment` ra khỏi hàng đợi → build câu theo template có thể
  cấu hình (placeholder `{name}`, `{content}`, cho phép thêm tiền tố/hậu tố tùy ý, ví dụ
  `"{name} hỏi: {content}"`) → gọi `vieneu.infer_stream(...)` với giọng đang chọn → phát qua
  thiết bị audio output đã chọn.
- Comment gây lỗi TTS (rỗng, chỉ emoji, ký tự không hợp lệ...) bị bỏ qua và ghi log, không
  làm crash worker.
- Giao tiếp về UI thread qua Qt Signal/Slot để tránh race condition khi cập nhật giao diện.

### 5. Quản lý giọng đọc (bao gồm voice cloning)
- Danh sách giọng gồm cả preset có sẵn của VieNeu-TTS và giọng do người dùng tự clone.
- "Thêm giọng mới": chọn file audio mẫu (3–8s) → đặt tên → `vieneu.add_voice(name, path,
  denoise=True)` → `save_voices()` để giọng clone còn tồn tại ở các lần chạy sau.
- Có thể xóa giọng clone khỏi danh sách (`remove_voice`).
- Chỉ một giọng được chọn làm giọng đọc chính tại một thời điểm (áp dụng cho mọi comment,
  không phân biệt theo người bình luận hay nền tảng).

### 6. UI (PySide6)
- **Panel kết nối**: ô nhập TikTok username + nút Connect/Disconnect; ô nhập YouTube
  URL/video ID + nút Connect/Disconnect riêng biệt. Cả hai có thể hoạt động đồng thời.
- **Panel Settings**:
  - Dropdown chọn giọng đọc (preset + clone).
  - Quản lý giọng clone (thêm/xóa) như mô tả ở trên.
  - Dropdown chọn thiết bị audio output.
  - Ô nhập template câu đọc.
  - Ô nhập YouTube API key.
- **Panel log**: danh sách cuộn hiển thị comment đến theo thời gian thực, kèm nhãn nền tảng
  và tên người bình luận, đánh dấu comment đang được đọc; hiển thị số lượng đang chờ trong
  hàng đợi.
- **Điều khiển đọc**: nút Start/Pause việc đọc bằng TTS mà không ngắt kết nối connector.

## Data flow

1. Connector nhận sự kiện comment thô từ nền tảng → chuẩn hóa thành `Comment` dataclass
   chung (`platform`, `author`, `text`, `ts`).
2. `Comment` được đẩy vào Shared Queue theo thứ tự đến.
3. TTS Worker lấy `Comment` ra, build câu theo template, đồng bộ gọi TTS, phát audio.
4. Đồng thời, mỗi `Comment` cũng được emit qua Qt Signal để Panel log hiển thị ngay khi
   nhận (độc lập với tốc độ đọc của TTS Worker).

## Xử lý lỗi & edge case

- TikTok/YouTube mất kết nối hoặc live kết thúc: hiển thị trạng thái rõ ràng, không tự động
  reconnect (MVP), người dùng chủ động Connect lại.
- YouTube API key sai / hết quota / video không live: báo lỗi cụ thể ngay tại panel liên
  quan.
- Lỗi TTS trên một comment cụ thể không làm gián đoạn các comment tiếp theo.
- Hàng đợi tồn đọng không bị drop; hiển thị số lượng chờ để người dùng chủ động biết độ trễ.

## Testing

- **Mock connector**: một connector giả phát sinh comment mẫu định kỳ, dùng để test toàn bộ
  luồng Queue → TTS → Audio → UI mà không cần một phiên live thật.
- **Unit test**:
  - Parser template (`{name}`/`{content}` → câu hoàn chỉnh, có prefix/suffix).
  - Hàng đợi FIFO giữ đúng thứ tự khi có nhiều nguồn đẩy vào đồng thời.
  - Chuẩn hóa `Comment` từ payload mẫu (fixture JSON) của TikTok và YouTube.
- **Test thủ công**: chạy thử với một phiên TikTok live thật và một phiên YouTube live thật
  trước khi coi MVP hoàn thành, bao gồm cả trường hợp cả hai nền tảng cùng chạy song song.

## Đóng gói & vận hành

- PyInstaller build riêng trên Windows và macOS, không cross-compile.
- Model VieNeu-TTS tải về từ HuggingFace ở lần chạy đầu tiên (cần mạng); sau đó ứng dụng
  chạy hoàn toàn offline (trừ kết nối tới TikTok/YouTube để lấy comment).
- Người dùng tự cấp và nhập YouTube Data API key của riêng họ (không đóng gói sẵn trong
  app).

## Ngoài phạm vi (out of scope cho bản thiết kế này)

- Shopee Live (không có API public, khó ổn định — để giai đoạn sau).
- Tự động phát hiện khi nào một kênh/username bắt đầu live (MVP chỉ kết nối thủ công).
- Lọc/ưu tiên comment theo từ khóa, bỏ spam/trùng lặp (MVP đọc tuần tự tất cả, không lọc).
- Gán giọng đọc khác nhau theo người bình luận hoặc theo nền tảng (MVP dùng một giọng chung
  tại một thời điểm).
- Tự động reconnect khi mất kết nối.
