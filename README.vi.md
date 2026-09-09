*[English](README.md) | Tiếng Việt*

# cmt-speak

Ứng dụng desktop (Windows/macOS) đọc to bình luận từ phiên live **TikTok** và **YouTube**
bằng giọng nói tiếng Việt tổng hợp cục bộ, dùng
[VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) — không cần gửi dữ liệu lên server nào,
chạy hoàn toàn offline sau lần tải model đầu tiên. Giúp streamer nghe và phản hồi bình luận
mà không cần liên tục nhìn màn hình chat.

Đây là dự án **mã nguồn mở**, phát triển và bảo trì trong thời gian rảnh. Mọi đóng góp về
code, issue, ý tưởng hay ủng hộ tài chính đều rất đáng quý — xem mục
[Ủng hộ dự án](#-ủng-hộ-dự-án) bên dưới.

## Tính năng

- **Kết nối đồng thời TikTok Live + YouTube Live**, mỗi nền tảng bật/tắt độc lập.
  - TikTok: chỉ cần nhập username, không cần API key.
  - YouTube: nhập URL/video ID live + API key riêng của bạn (YouTube Data API v3).
- **Đọc bình luận bằng giọng Việt tự nhiên**, tổng hợp cục bộ bằng VieNeu-TTS (CPU/ONNX hoặc
  GPU nếu có), không phụ thuộc dịch vụ TTS trả phí bên ngoài.
- **Voice cloning**: tự thêm giọng đọc mới từ một đoạn audio mẫu 3–8 giây, đặt tên và dùng
  lại ở các lần chạy sau; xoá giọng clone khi không cần.
- **Mẫu câu đọc tuỳ chỉnh** (template) với placeholder `{name}`, `{content}`, ví dụ:
  `"{name} hỏi: {content}"`.
- **Chọn thiết bị audio output**, hỗ trợ route qua virtual audio cable để đưa thẳng vào OBS.
- **Hàng đợi chung, không rớt bình luận**: hai connector đẩy bình luận vào một hàng đợi
  FIFO duy nhất, đọc tuần tự theo đúng thứ tự đến; số lượng đang chờ hiển thị trực tiếp trên
  UI.
- **Bộ lọc bình luận** (blocklist từ khoá) để tránh đọc nội dung không mong muốn.
- **Log realtime** hiển thị toàn bộ bình luận nhận được, đánh dấu bình luận đang được đọc,
  kèm nhãn nền tảng và tên người bình luận.
- Một connector mất kết nối không ảnh hưởng connector còn lại hay hàng đợi chung; trạng thái
  lỗi (API key sai, hết quota, video không live...) hiển thị rõ ràng ngay trên UI.

## Kiến trúc tổng quan

```
TikTok Connector ──┐
                    ├─▶ Shared Queue (FIFO) ──▶ TTS Worker ──▶ VieNeu-TTS ──▶ Audio output
YouTube Connector ──┘                                │
                                                       ▼
                                                  PySide6 UI (log, controls, settings)
```

Chi tiết thiết kế và kế hoạch triển khai:

- [Thiết kế tổng thể](docs/superpowers/specs/2026-09-09-cmt-speak-design.md) /
  [Kế hoạch triển khai](docs/superpowers/plans/2026-09-09-cmt-speak-plan.md)
- [Thiết kế quick controls, filter, reconnect](docs/superpowers/specs/2026-09-09-quick-controls-filter-reconnect-design.md)
- [Thiết kế UI redesign](docs/superpowers/specs/2026-09-09-ui-redesign-design.md)

## Yêu cầu hệ thống

- Windows hoặc macOS.
- [uv](https://docs.astral.sh/uv/) và Python 3.12 (uv tự tải Python nếu máy chưa có).
- Kết nối mạng cho lần chạy đầu tiên (tải model VieNeu-TTS từ Hugging Face) và khi kết nối
  TikTok/YouTube để lấy bình luận. Các lần chạy sau không cần mạng để tổng hợp giọng nói.
- (Tuỳ chọn) API key YouTube Data API v3 nếu muốn đọc bình luận YouTube Live.

## Cài đặt & chạy

```bash
uv sync
uv run python -m cmtspeak
```

## Chạy test

```bash
uv run pytest -q
```

## Đóng gói (PyInstaller)

Spec dùng chung cho cả Windows và macOS: [packaging/cmt-speak.spec](packaging/cmt-speak.spec).
Luôn build trên đúng OS đích (không cross-compile).

```bash
uv run pyinstaller --noconfirm packaging/cmt-speak.spec
```

- **macOS**: kết quả là `dist/cmt-speak.app`, chạy bằng
  `open dist/cmt-speak.app` hoặc trực tiếp
  `dist/cmt-speak.app/Contents/MacOS/cmt-speak`.
- **Windows**: kết quả là `dist/cmt-speak/cmt-speak.exe` (BUNDLE của spec chỉ áp dụng cho
  macOS, PyInstaller tự bỏ qua bước này trên Windows).

Lần chạy đầu tiên trên máy mới cần mạng để VieNeu-TTS tải model từ Hugging Face; các lần
sau chạy hoàn toàn offline (trừ việc kết nối TikTok/YouTube để lấy bình luận).

## Đóng góp

Dự án hoan nghênh mọi đóng góp:

1. Fork repo, tạo branch riêng cho thay đổi của bạn.
2. Chạy `uv run pytest -q` trước khi commit để đảm bảo không phá vỡ test hiện có.
3. Mở Pull Request mô tả rõ vấn đề cần giải quyết và cách bạn giải quyết.

Nếu phát hiện lỗi hoặc có đề xuất tính năng, hãy tạo
[Issue](https://github.com/tuannda98/TTS_LiveComment/issues) trên GitHub.

## 💛 Ủng hộ dự án

cmt-speak là dự án mã nguồn mở miễn phí, phát triển ngoài giờ làm việc. Nếu ứng dụng hữu ích
với bạn (đặc biệt nếu bạn là streamer đang dùng nó trong buổi live), một lời cảm ơn nhỏ sẽ là
động lực rất lớn để mình tiếp tục bảo trì và phát triển thêm tính năng mới:

- ☕ **Buy Me a Coffee**: [buymeacoffee.com/mrt198](https://buymeacoffee.com/mrt198)
- 💳 **PayPal**: [paypal.me/mrt198](https://paypal.me/mrt198)
- 🏦 **Chuyển khoản ngân hàng (VN)**: MBBank — STK `866881998` — Chủ TK
  `NGUYEN DUC ANH TUAN`

  <img src="docs/assets/donate-qr.png" alt="VietQR chuyển khoản MBBank" width="240" />

  *(Quét mã bằng app ngân hàng bất kỳ hỗ trợ VietQR/Napas 247)*

Mọi khoản ủng hộ, dù nhỏ, đều được trân trọng. Cảm ơn bạn đã sử dụng và đồng hành cùng dự án!
