# cmt-speak — Implementation Plan

Dựa trên [2026-09-09-cmt-speak-design.md](../specs/2026-09-09-cmt-speak-design.md). Mỗi
phase làm ra một lát cắt chạy được và kiểm chứng độc lập trước khi sang phase kế tiếp.

## Cấu trúc project dự kiến

```
cmt-speak/
  pyproject.toml
  src/cmtspeak/
    __init__.py
    main.py                    # entry point, khởi tạo QApplication
    config.py                  # đọc/ghi settings (API key, template, voice, device)
    models.py                  # Comment dataclass
    queue_bus.py               # CommentQueue: hàng đợi thread-safe + phát Qt signal
    connectors/
      base.py                  # interface Connector
      mock_connector.py
      tiktok_connector.py
      youtube_connector.py
    tts/
      template.py              # format câu đọc từ template
      voice_manager.py         # preset voices + clone voices (wrap vieneu)
      worker.py                # TTSWorker thread
    audio/
      output.py                # liệt kê + phát audio ra device chọn (sounddevice)
    ui/
      main_window.py
      connection_panel.py
      settings_panel.py
      log_panel.py
  tests/
    fixtures/
      tiktok_comment.json
      youtube_liveChatMessage.json
    test_template.py
    test_queue_bus.py
    test_normalize_tiktok.py
    test_normalize_youtube.py
    test_voice_manager.py
```

## Phase 0 — Bootstrap project

- Khởi tạo `pyproject.toml` (dùng `uv`), thêm dependency: `PySide6`, `sounddevice`,
  `TikTokLive`, `google-api-python-client`, `vieneu`, `pytest`.
- Tạo skeleton package `src/cmtspeak` theo cấu trúc trên, `main.py` chỉ mở một cửa sổ
  Qt trống.
- **Kiểm chứng**: `uv run python -m cmtspeak` mở được cửa sổ trống, không lỗi.

## Phase 1 — Data model & shared queue

- `models.py`: `Comment` dataclass (`platform: str`, `author: str`, `text: str`,
  `ts: float`).
- `queue_bus.py`: `CommentQueue` bọc `queue.Queue`, method `put(comment)` gọi được từ bất
  kỳ thread nào, phát Qt signal `comment_received` (queued connection) để UI thread nhận an
  toàn; method `get()` cho consumer; property `size` cho UI hiển thị số lượng đang chờ.
- **Test**: `test_queue_bus.py` — nhiều thread cùng `put()`, `get()` phải trả về đúng thứ tự
  đến (FIFO) và `size` phản ánh đúng.
- **Kiểm chứng**: chạy `pytest tests/test_queue_bus.py` pass.

## Phase 2 — Connector interface, Mock connector, Template formatter

- `connectors/base.py`: interface `Connector` với `start()`, `stop()`, nhận một
  `CommentQueue` để đẩy comment vào, có `status_changed` signal
  (`connecting|connected|error|disconnected`, kèm message lỗi nếu có).
- `connectors/mock_connector.py`: sinh comment mẫu định kỳ (vd mỗi 1–2s, xoay vòng một
  danh sách câu mẫu tiếng Việt), dùng để phát triển/test không cần live thật.
- `tts/template.py`: `format_message(comment, template) -> str`, hỗ trợ placeholder
  `{name}`, `{content}`, giữ nguyên phần chữ khác trong template làm tiền tố/hậu tố.
- **Test**: `test_template.py` — vài template mẫu (`"{name} nói: {content}"`, chỉ
  `"{content}"`, có tiền tố/hậu tố cố định) cho ra đúng chuỗi kỳ vọng.
- **Kiểm chứng**: script thủ công chạy `MockConnector` → in ra console câu đã format theo
  đúng thứ tự, đúng nội dung.

## Phase 3 — VieNeu-TTS integration & audio playback

- `tts/voice_manager.py`: wrap `vieneu.Vieneu()`; `list_voices()` trả về preset voices từ
  `list_preset_voices()`.
- `audio/output.py`: `list_output_devices()` dùng `sounddevice.query_devices()`;
  `play(audio_chunks, device_index)` phát buffer float32 ra device chỉ định.
- `tts/worker.py`: `TTSWorker` (QThread hoặc `threading.Thread` + Qt signal để báo
  "đang đọc: <comment>"), vòng lặp: lấy từ `CommentQueue` → format template → gọi
  `vieneu.infer_stream(text, voice=...)` → phát từng chunk qua `AudioOutput`. Bắt exception
  quanh từng comment (text rỗng, lỗi TTS...) → log cảnh báo, tiếp tục vòng lặp, không dừng
  worker.
- **Kiểm chứng thủ công**: chạy `MockConnector` → nghe được audio đọc ra loa mặc định theo
  đúng giọng preset chọn trước.

## Phase 4 — Voice cloning management

- Mở rộng `voice_manager.py`: `add_clone_voice(name, wav_path)` gọi
  `vieneu.add_voice(name, wav_path, denoise=True)` rồi `save_voices()`;
  `remove_clone_voice(name)` gọi `remove_voice`; `list_voices()` gộp cả preset và giọng
  clone đã lưu.
- `config.py`: lưu danh sách tên giọng clone hiện có (metadata nhẹ, giọng thật do
  `vieneu.save_voices()` quản lý file riêng) để load lại đúng trạng thái khi mở app.
- **Test**: `test_voice_manager.py` — stub/mock lời gọi `vieneu.add_voice`/`remove_voice`
  để test logic thêm/xóa và đồng bộ với config, không phụ thuộc mô hình TTS thật (chạy
  nhanh, không cần audio mẫu thật).
- **Kiểm chứng thủ công**: dùng một file audio mẫu thật (3–8s), thêm giọng clone, chọn giọng
  đó làm giọng đọc, xác nhận nghe được giọng đã clone khi có comment mới; xóa giọng, xác
  nhận biến mất khỏi danh sách.

## Phase 5 — TikTok connector (thật)

- `connectors/tiktok_connector.py`: chạy `TikTokLive` client trong một asyncio event loop
  riêng (thread nền); khi nhận event comment → chuẩn hóa thành `Comment(platform="tiktok",
  ...)` → đẩy vào `CommentQueue`; bắt exception khi mất kết nối/live kết thúc → phát
  `status_changed("disconnected"/"error", message)`. Không tự động reconnect.
- **Test**: `test_normalize_tiktok.py` — dùng fixture giả lập payload/event của
  `TikTokLive` (`tests/fixtures/tiktok_comment.json`), kiểm tra hàm chuẩn hóa cho ra đúng
  `Comment`. Không test kết nối mạng thật.
- **Kiểm chứng thủ công**: kết nối tới một username đang live thật trên TikTok, xác nhận
  comment xuất hiện trong console/log và được đọc bằng TTS.

## Phase 6 — YouTube connector (thật)

- `connectors/youtube_connector.py`: nhận API key + video ID/URL; gọi `videos.list` để lấy
  `liveChatId`; vòng lặp polling `liveChatMessages.list` theo đúng `pollingIntervalMillis`
  trả về; chuẩn hóa mỗi message thành `Comment(platform="youtube", ...)`; bắt lỗi cụ thể
  (API key sai, video không live, hết quota) → `status_changed("error", message)` với thông
  điệp rõ ràng cho từng loại lỗi.
- **Test**: `test_normalize_youtube.py` — dùng fixture JSON mẫu response của
  `liveChatMessages.list` (`tests/fixtures/youtube_liveChatMessage.json`), kiểm tra hàm
  chuẩn hóa. Không gọi API thật trong test.
- **Kiểm chứng thủ công**:
  - Kết nối tới một video YouTube đang live thật, xác nhận comment xuất hiện và được đọc.
  - Chạy đồng thời TikTok connector (phase 5) + YouTube connector, xác nhận comment từ cả
    hai nền tảng cùng vào một hàng đợi chung theo đúng thứ tự đến, không bên nào chặn bên
    kia khi một bên mất kết nối.

## Phase 7 — Lắp ráp UI (PySide6)

- `ui/connection_panel.py`: ô nhập TikTok username + Connect/Disconnect; ô nhập YouTube
  URL/video ID + Connect/Disconnect riêng biệt; hiển thị trạng thái từng connector
  (connecting/connected/error kèm message).
- `ui/settings_panel.py`: dropdown giọng đọc (preset + clone), khu vực thêm/xóa giọng clone
  (chọn file, đặt tên), dropdown thiết bị audio output, ô template câu đọc, ô nhập YouTube
  API key. Lưu mọi thay đổi qua `config.py`, load lại khi mở app.
- `ui/log_panel.py`: danh sách cuộn hiển thị `Comment` đến theo thời gian thực (nhãn nền
  tảng + tên), highlight item đang được `TTSWorker` đọc (qua signal "đang đọc"), hiển thị
  số lượng đang chờ (`CommentQueue.size`).
- `ui/main_window.py`: ráp 3 panel trên + nút Start/Pause việc đọc (dừng `TTSWorker` tiêu
  thụ hàng đợi mà không ngắt connector).
- **Kiểm chứng thủ công**: đi hết luồng — mở app, cấu hình giọng/template/device, kết nối cả
  hai nền tảng, thấy log cập nhật realtime, nghe TTS đọc đúng comment đang highlight, bấm
  Pause/Start hoạt động đúng, Disconnect từng nền tảng độc lập.

## Phase 8 — Đóng gói

- Viết PyInstaller spec riêng cho Windows và macOS (khác nhau về icon/entry nếu cần).
- Ghi lại các bước build cho từng OS (README ngắn gọn trong repo).
- **Kiểm chứng**: build ra file thực thi độc lập trên ít nhất một OS, chạy ngoài môi trường
  dev, xác nhận app khởi động, tự tải model VieNeu-TTS lần đầu (cần mạng), sau đó hoạt động
  offline với TTS (chỉ TikTok/YouTube cần mạng).

## Phase 9 — Rà soát cuối theo design doc

- Đối chiếu lại mục "Testing" và "Ngoài phạm vi" trong design doc: xác nhận không có
  auto-reconnect, không lọc/ưu tiên comment, không có Shopee, mỗi thời điểm chỉ một giọng
  đọc áp dụng cho mọi comment.
- Chạy toàn bộ `pytest`, đảm bảo pass.
- Test tay lần cuối với một phiên TikTok live thật + một phiên YouTube live thật chạy song
  song, đọc liên tục không rớt comment, không crash worker khi gặp comment lỗi (emoji-only,
  ký tự đặc biệt).
