# Thiết kế: Làm mới UI cmt-speak theo phong cách streaming/creator tools

## Bối cảnh

UI hiện tại (sau [Phase "Settings as tabbed dialog + menu bar"](../../../src/cmtspeak/ui/main_window.py))
dùng widget Qt mặc định, không style riêng: nút text thuần, `QListWidget` cho log
bình luận với prefix emoji (⏳🔊✓🚫), cửa sổ chính gọn (kết nối + điều khiển + log)
và một dialog "Cài đặt" tách biệt mở từ menu bar, có tab con (Giọng đọc/Bộ lọc nội
dung/Chung) và nút "Lưu cài đặt" riêng.

Mục tiêu: làm mới giao diện để trông giống các ứng dụng streaming/creator tool hiện
có trên thị trường (Streamlabs, StreamElements, TikTok Live Studio, Restream) — dark
theme, sidebar điều hướng, card, icon SVG, status pill màu — mà không thay đổi logic
nghiệp vụ (kết nối, hàng đợi, TTS worker, filter...).

## Phạm vi

- Trong phạm vi: dựng lại toàn bộ lớp UI (`src/cmtspeak/ui/`) theo cấu trúc mới,
  thêm hệ theme (QSS + màu + icon), gộp dialog Cài đặt vào cửa sổ chính dạng
  sidebar, đổi hành vi lưu cấu hình từ "bấm Lưu" sang lưu tức thì.
- Ngoài phạm vi: mọi thay đổi logic ở `connectors/`, `tts/`, `audio/`, `queue_bus.py`,
  `config.py`, `models.py`. Không đổi cấu trúc `Config` (vẫn dùng `get`/`set`/`save`).
  Không làm custom frameless window (giữ title bar gốc của OS).

## Kiến trúc

Giữ nguyên `MainWindow` làm entry point nhưng đổi cấu trúc bên trong:

```
MainWindow (QMainWindow, không còn menu bar chức năng)
├── QWidget trung tâm
│   └── QHBoxLayout
│       ├── Sidebar (nav trái, cố định ~200px)
│       └── QStackedWidget
│           ├── LivePage       (mới — thay ConnectionPanel + controls + LogPanel cũ)
│           ├── VoicesPage     (nội dung tab "Giọng đọc" cũ, tách khỏi SettingsPanel)
│           ├── FilterPage     (nội dung tab "Bộ lọc nội dung" cũ)
│           └── GeneralPage    (nội dung tab "Chung" cũ)
```

`SettingsPanel` (QDialog) bị xoá; nội dung 3 tab của nó trở thành 3 page riêng,
mỗi page implement lưu tức thì (gọi `cfg.set(...)` + `cfg.save()` ngay khi field đổi,
qua `textChanged`/`currentIndexChanged`/... thay vì một nút "Lưu cài đặt" tổng).
`LogPanel` và `ConnectionPanel` được giữ lại về mặt logic (API `add_comment`,
`set_now_reading`, `mark_removed`...) nhưng style/bố cục bên trong đổi hoàn toàn
sang card + status pill; `LogPanel` không còn dùng emoji prefix mà dùng viền trái
màu theo trạng thái.

Menu bar: trên macOS, Qt tự đưa "Quit"/"About" vào application menu mặc định dù
không tạo `menuBar()` — nếu cần entry "Về..." tường minh, thêm một `QMenu` ẩn tối
thiểu chỉ chứa "Thoát" và "Giới thiệu" (không có mục "Cài đặt" nữa vì đã lên sidebar).

### Module mới: `src/cmtspeak/ui/theme.py`

- `PALETTE`: dict hằng số màu (xem bảng màu bên dưới).
- `STYLESHEET`: chuỗi QSS áp cho toàn ứng dụng qua `app.setStyleSheet(...)`, style
  hoá `QPushButton`, `QLineEdit`, `QComboBox`, `QListWidget`, `QSpinBox`, card
  container (`QFrame[class="card"]` qua `setProperty("class", "card")`), sidebar
  item đang chọn, v.v.
- `load_icon(name: str, color: str = PALETTE["text_primary"]) -> QIcon`: đọc file
  SVG trong `src/cmtspeak/assets/icons/<name>.svg`, thay `currentColor`/fill bằng
  `color` được truyền vào (SVG nguồn dùng `fill="currentColor"`, tô lại bằng string
  replace trước khi nạp vào `QSvgRenderer` rồi render ra `QPixmap`/`QIcon`), cache
  theo `(name, color)` để không phải render lại mỗi lần gọi.

### Assets mới: `src/cmtspeak/assets/icons/`

Bộ icon SVG (giấy phép MIT, ví dụ Lucide) đơn sắc `fill="currentColor"`, tối thiểu:
`radio.svg`, `mic-2.svg`, `filter.svg`, `settings.svg`, `play.svg`, `pause.svg`,
`skip-forward.svg`, `trash-2.svg`, `plug.svg`, `plug-zap.svg`, `volume-2.svg`,
`key.svg`, `folder-open.svg`, `plus.svg`, `pencil.svg`, `x.svg`, `check.svg`.

## Bảng màu (dark theme, cố định — không có light mode)

| Token | Giá trị | Dùng cho |
|---|---|---|
| `bg_window` | `#0f1115` | Nền cửa sổ chính |
| `bg_sidebar` | `#161922` | Nền sidebar |
| `bg_card` | `#1c1f29` | Nền card/panel trong mỗi page |
| `border` | `#2a2e3a` | Viền card, input, divider |
| `text_primary` | `#e6e8ee` | Chữ chính |
| `text_secondary` | `#9198a8` | Chữ phụ, placeholder |
| `text_muted` | `#5b6172` | Chữ disabled |
| `accent` | `#6c5ce7` | Nút chính, mục sidebar đang chọn, viền trái "đang đọc" |
| `status_success` | `#22c55e` | "Đã kết nối", trạng thái live |
| `status_pending` | `#f5a623` | "Đang kết nối...", "Đang kết nối lại", trạng thái chờ đọc |
| `status_error` | `#ef4444` | "Lỗi", đã xóa/đã bỏ qua |
| `platform_tiktok` | `#ff2d55` | Badge nền tảng TikTok |
| `platform_youtube` | `#ff0000` | Badge nền tảng YouTube |

Typography: font hệ thống mặc định của Qt trên từng OS (không nhúng font riêng).
Cỡ chữ: 13px nội dung, 11px caption/hint, 15px semi-bold tiêu đề mục trong page.
Bo góc: 8px card/input, 6px nút, pill (radius lớn, `999px`-style) cho status badge
và badge nền tảng. Spacing scale: 4/8/12/16/24px cho margin/padding/gap.

## Bố cục & component từng phần

### Sidebar

`QWidget` rộng cố định ~200px, nền `bg_sidebar`, chứa 4 nút nav dạng
`QToolButton` (icon trái + text, checkable, exclusive group) xếp dọc:
**Live** (icon `radio`), **Giọng đọc** (`mic-2`), **Bộ lọc nội dung** (`filter`),
**Chung** (`settings`). Mục đang chọn có nền `accent` mờ (alpha thấp) + chữ
`text_primary`; mục khác dùng `text_secondary`. Cuối sidebar (đẩy xuống đáy bằng
stretch) hiển thị "cmt-speak vX.Y.Z" cỡ chữ caption, màu `text_muted`.

Click một mục → `stacked_widget.setCurrentWidget(...)`. Trang mặc định khi mở app:
**Live**.

### LivePage

Thay thế `ConnectionPanel` + hàng nút điều khiển + `LogPanel` trong `MainWindow`
cũ bằng một page:

1. **Connection cards** (hàng ngang, 2 card bằng nhau): mỗi card là `QFrame`
   class="card" chứa: icon nền tảng + tên platform (label đậm), `QLineEdit` input,
   nút Kết nối/Ngắt kết nối, và **status pill** — một `QLabel` nhỏ dạng pill với
   chấm màu (`●`, tô bằng màu status tương ứng) + text trạng thái, thay hoàn toàn
   `status_label` text-only cũ. Giữ nguyên toàn bộ logic hiện có của
   `ConnectorRow`/`ConnectionPanel` (state machine connect/disconnect, các callback
   `_on_status_changed`...), chỉ đổi cách hiển thị trạng thái (map status string →
   màu pill thay vì chỉ đổi text).
2. **Thanh điều khiển phát**: hàng ngang gồm 3 nút icon+text (Tạm dừng/Tiếp tục —
   icon đổi `play`/`pause` theo state, Bỏ qua — icon `skip-forward`, Xóa hàng đợi —
   icon `trash-2`), cộng một badge tròn nhỏ hiển thị số lượng đang chờ đọc (lấy từ
   `queue_size_label` cũ, chuyển thành pill số ở cuối hàng thay vì label riêng phía
   trên danh sách).
3. **Danh sách bình luận**: vẫn `QListWidget` (giữ nguyên toàn bộ logic
   `LogPanel` — `_pending_items`, các state PENDING/READING/READ/REMOVED, các
   method `add_comment`/`set_now_reading`/`set_finished_reading`/`set_filtered`/
   `mark_removed`), chỉ đổi `_set_status`: thay vì prefix emoji, style mỗi item
   bằng `QListWidgetItem.setData` cho một badge nền tảng màu (`platform_tiktok`/
   `platform_youtube`) vẽ ở đầu dòng và một dải màu viền trái theo trạng thái
   (`status_pending` cho PENDING, `accent` + nền nhạt cho READING đang đọc,
   `text_muted` cho READ, `status_error` cho REMOVED) — thực hiện bằng
   `QStyledItemDelegate` tùy chỉnh vẽ viền trái + badge, vì `QListWidgetItem`
   thuần không hỗ trợ border riêng từng cạnh.

### VoicesPage (trước là tab "Giọng đọc" trong SettingsPanel)

Giữ nguyên toàn bộ: `voice_list`, `demo_text_edit`, `demo_button`,
`edit_clone_button`, `remove_clone_button`, khung thêm giọng clone,
`_VoiceListLoader`/`_VoiceDemoWorker`. Đổi trình bày: bọc trong card, giọng clone
hiển thị badge pill nhỏ "Clone" màu `accent` cạnh tên thay cho hậu tố text
`"  (Clone)"`. Không có nút Lưu — lựa chọn giọng ghi vào Config ngay khi
`currentItemChanged` (thay vì chỉ khi bấm Lưu như cũ).

### FilterPage (trước là tab "Bộ lọc nội dung")

Hai card: (1) danh sách từ cấm + input thêm + nút Thêm/Xóa/Import/Xem mẫu, giữ
nguyên `_SampleBlocklistDialog` và toàn bộ hàm `_on_add_blocklist_entry` v.v.;
(2) card cấu hình gồm `blocklist_mode_combo`, `dedup_mode_combo`,
`dedup_window_spin`. Mỗi thay đổi (thêm/xóa từ, đổi combo, đổi spin) gọi
`cfg.set(...)` + `cfg.save()` ngay lập tức thay vì gom vào lúc bấm Lưu.

### GeneralPage (trước là tab "Chung")

Một card dạng form: thiết bị audio (`device_combo` + nút Làm mới), mẫu câu đọc
(`template_edit` + hint), YouTube API key (`api_key_edit`), hành vi nút "Bỏ qua"
(`skip_mode_combo`). Không đổi field nào. Mỗi field lưu tức thì qua tín hiệu
`textChanged`/`currentIndexChanged` tương ứng (debounce nhẹ ~300ms cho các
`QLineEdit` bằng `QTimer` để tránh ghi file liên tục khi đang gõ).

## Luồng dữ liệu

Không đổi: `Config` vẫn là nguồn sự thật duy nhất, `TTSWorker`/connector vẫn đọc
`Config` mới nhất tại thời điểm dùng. Điểm khác duy nhất so với trước: các page
mới tự gọi `cfg.set()` + `cfg.save()` ngay khi giá trị đổi (thay vì gom lại chờ
nút Lưu) — không cần cơ chế thông báo thêm vì không có state trung gian nào khác
phụ thuộc vào "đã lưu hay chưa".

## Xử lý lỗi

Không đổi hành vi lỗi hiện có (cảnh báo qua `QMessageBox`, status bar cho worker
warning). `load_icon` nếu không tìm thấy file SVG tương ứng thì trả về `QIcon()`
rỗng (không crash) — icon sẽ trống nhưng không ảnh hưởng chức năng, hữu ích khi
thêm nhầm tên icon lúc phát triển.

## Kiểm thử

- Test hiện có (`tests/test_connection_panel.py`, `tests/test_log_panel.py`)
  cần rà lại: các test này thao tác trực tiếp API của `ConnectionPanel`/`LogPanel`
  (không phải qua UI cũ của `MainWindow`) nên dự kiến vẫn chạy được nếu giữ
  nguyên chữ ký các method public; phần assert liên quan tới text hiển thị của
  status label (nếu có) cần cập nhật cho khớp cấu trúc status pill mới.
  Nếu `_set_status` của LogPanel đổi sang dùng delegate, test hiện tại đọc
  `item.text()`/màu qua `item.foreground()` cần được viết lại cho phù hợp cách
  hiển thị mới.
- Thêm test cho `theme.load_icon`: trả về `QIcon` hợp lệ với tên icon có thật,
  trả về icon rỗng (không raise) với tên không tồn tại.
- Kiểm thử thủ công bằng cách chạy `uv run python -m cmtspeak`, xác nhận: chuyển
  trang sidebar hoạt động, kết nối/ngắt kết nối TikTok/YouTube vẫn hoạt động và
  status pill đổi màu đúng, lưu tức thì các field ở 3 page cấu hình (tắt mở lại
  app để xác nhận Config đã ghi), danh sách bình luận hiển thị đúng badge/viền
  theo trạng thái.
