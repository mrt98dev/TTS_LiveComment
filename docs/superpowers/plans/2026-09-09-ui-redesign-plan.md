# Làm mới UI cmt-speak — Implementation Plan

Dựa trên [2026-09-09-ui-redesign-design.md](../specs/2026-09-09-ui-redesign-design.md).
Mỗi phase làm ra một lát cắt chạy được, kiểm chứng độc lập trước khi sang phase kế.

## Song song hóa

Phase 0 (theme + icon, nền tảng cho mọi phase khác) phải làm **tuần tự trước**.
Sau đó 4 nhánh độc lập file có thể chạy song song, vì mỗi nhánh chỉ đụng file
riêng của mình và chỉ phụ thuộc `ui/theme.py` đã xong ở Phase 0:

- **Nhánh A** — Phase 1-3: Trang Live (`ConnectionPanel` status pill, control
  bar, `LogPanel` delegate)
- **Nhánh B** — Phase 4: `VoicesPage` (tách từ tab "Giọng đọc" cũ)
- **Nhánh C** — Phase 5: `FilterPage` (tách từ tab "Bộ lọc nội dung" cũ)
- **Nhánh D** — Phase 6: `GeneralPage` (tách từ tab "Chung" cũ)

Phase 7 (dựng `MainWindow` mới: sidebar + `QStackedWidget`, xoá `SettingsPanel`)
làm sau khi cả 4 nhánh xong, vì nó ráp tất cả các page lại và xoá code cũ. Phase 8
rà soát cuối.

## Phase 0 — Nền tảng: `ui/theme.py` + bộ icon SVG

- `src/cmtspeak/assets/icons/`: thêm 17 file SVG đơn sắc (`fill="currentColor"`,
  viewBox vuông, style Lucide — có thể vendor trực tiếp từ Lucide, giấy phép ISC/MIT,
  ghi nguồn trong `src/cmtspeak/assets/icons/NOTICE.md`): `radio.svg`, `mic-2.svg`,
  `filter.svg`, `settings.svg`, `play.svg`, `pause.svg`, `skip-forward.svg`,
  `trash-2.svg`, `plug.svg`, `plug-zap.svg`, `volume-2.svg`, `key.svg`,
  `folder-open.svg`, `plus.svg`, `pencil.svg`, `x.svg`, `check.svg`.
- `src/cmtspeak/ui/theme.py` (mới):
  - `PALETTE: dict[str, str]` — đúng token/giá trị màu trong bảng của design doc
    (`bg_window`, `bg_sidebar`, `bg_card`, `border`, `text_primary`,
    `text_secondary`, `text_muted`, `accent`, `status_success`, `status_pending`,
    `status_error`, `platform_tiktok`, `platform_youtube`).
  - `STYLESHEET: str` — QSS áp toàn cục: nền cửa sổ/sidebar, `QPushButton` (nút
    thường + nút primary qua `setProperty("class", "primary")`), `QLineEdit`,
    `QComboBox`, `QSpinBox`, `QListWidget`, khung card qua
    `QFrame[class="card"]` (bo góc 8px, viền `border`, nền `bg_card`, padding
    16px), nút sidebar qua `QToolButton[class="nav-item"]` (state
    checked dùng nền `accent` alpha thấp).
  - `ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"`.
  - `load_icon(name: str, color: str = PALETTE["text_primary"], size: int = 20) ->
    QIcon`: đọc `ICONS_DIR / f"{name}.svg"`, nếu không tồn tại trả `QIcon()`
    (không raise); nếu tồn tại, thay `currentColor` bằng `color` trong nội dung
    SVG (string replace), nạp bằng `QSvgRenderer`, render ra `QPixmap` kích
    thước `size×size` (nền trong suốt), bọc `QIcon`. Cache theo `(name, color,
    size)` bằng `functools.lru_cache` trên một hàm nội bộ nhận tham số đã chuẩn
    hoá (đường dẫn không đổi giữa các lần gọi nên cache an toàn).
- **Test**: `tests/test_theme.py` (mới) — `load_icon` với tên có thật trả về
  `QIcon` không rỗng (`icon.availableSizes()` không trống hoặc
  `not icon.isNull()`); với tên không tồn tại trả `QIcon()` và không raise; gọi
  2 lần cùng tham số trả cùng instance đã cache (kiểm qua `id(...)` hoặc đếm số
  lần đọc file bằng mock).
- **Kiểm chứng**: `pytest tests/test_theme.py` pass; import `theme` module độc
  lập (không cần `QApplication` chạy) không lỗi — `QIcon`/`QPixmap` cần một
  `QApplication` instance tồn tại để dùng, nên test phải dùng fixture `qapp`
  đã có sẵn trong `tests/conftest.py` (kiểm tra file này trước, thêm fixture
  nếu chưa có).

## Nhánh A — Phase 1-3: Trang Live

### Phase 1 — Status pill cho `ConnectionPanel`
- `ui/connection_panel.py`: trong `ConnectorRow`, thay `self.status_label`
  (hiện là `QLabel` text thuần) bằng một `QLabel` được style như pill qua
  `setProperty("class", "status-pill")` + `setProperty("status", <trạng thái>)`
  (giá trị: `"disconnected"`, `"connecting"`, `"connected"`, `"reconnecting"`,
  `"error"`), rồi trong `theme.STYLESHEET` thêm rule
  `QLabel[class="status-pill"][status="connected"] { color: <status_success>; }`
  v.v. cho từng giá trị `status`. `_on_status_changed` và `_reset()` giữ nguyên
  logic quyết định trạng thái, chỉ thêm dòng `self.status_label.setProperty(
  "status", ...)` + `self.status_label.style().unpolish/polish(...)` để Qt áp
  lại QSS khi property đổi lúc runtime.
- Bọc mỗi `ConnectorRow` (TikTok/YouTube) trong một `QFrame` class="card" ở
  `ConnectionPanel.__init__`, thêm icon nền tảng (`load_icon("plug", ...)` tạm
  thời — icon nền tảng cụ thể hơn để ở Phase 3 khi làm badge trong log) cạnh
  tiêu đề `<b>TikTok Live</b>`/`<b>YouTube Live</b>`.
- **Test**: `tests/test_connection_panel.py` — thêm/cập nhật case xác nhận
  `status_label.property("status")` đổi đúng giá trị qua các bước
  connect → connected → disconnect, và khi connector tự báo lỗi/disconnected.
  Nếu test hiện tại assert `status_label.text()` bằng chuỗi tiếng Việt cũ
  (`"Đã kết nối"`...), giữ nguyên các assert đó (text hiển thị không đổi, chỉ
  thêm property màu) — chỉ bổ sung, không xoá assert cũ.
- **Kiểm chứng thủ công**: chưa chạy được toàn app ở phase này (MainWindow
  chưa ráp lại) — viết một script tay nhỏ trong `scratchpad` dựng riêng
  `ConnectionPanel` trong một `QMainWindow` tạm, áp `theme.STYLESHEET`, xác
  nhận pill đổi màu đúng khi bấm Kết nối với `MockConnector`.

### Phase 2 — Thanh điều khiển phát dạng icon+text
- `ui/main_window.py` (tạm thời vẫn là file cũ, sẽ bị thay ở Phase 7): tách 3
  nút `pause_button`/`skip_button`/`clear_queue_button` thành một `QWidget`
  riêng mới `ui/playback_controls.py` (`PlaybackControls`), nhận `queue`
  (để hiển thị badge số lượng chờ đọc, subscribe `queue.comment_received` +
  cần thêm signal cho biết queue rỗng bớt — dùng cách đơn giản: một
  `QTimer` polling `queue.size` mỗi 500ms để cập nhật badge, tránh phải thêm
  signal mới vào `CommentQueue`). Mỗi nút dùng `load_icon(...)` +
  `setText(...)` (icon trái, text phải): Tạm dừng/Tiếp tục (`pause`/`play`,
  đổi icon theo `toggled`), Bỏ qua (`skip-forward`), Xóa hàng đợi (`trash-2`).
  Giữ nguyên toàn bộ logic hiện có của `_on_pause_toggled`/`_on_skip_clicked`/
  `_on_clear_queue_clicked` (di chuyển nguyên xi vào class mới, nhận
  `worker`/`cfg`/`queue`/`log_panel` qua constructor hoặc setter).
  Expose signal `warning` nếu cần chuyển tiếp cảnh báo lên status bar của
  `MainWindow`.
- **Test**: không có test Qt-signal riêng cho phase này trong bộ hiện tại;
  thêm `tests/test_playback_controls.py` tối thiểu kiểm badge số lượng cập
  nhật đúng khi `queue` thay đổi kích thước (gọi trực tiếp method cập nhật
  thay vì đợi `QTimer` thật, để test nhanh và không cần chờ 500ms).
- **Kiểm chứng thủ công**: script tay tương tự Phase 1, dựng `PlaybackControls`
  độc lập, bấm từng nút xác nhận hành vi giống hệt bản cũ.

### Phase 3 — Delegate cho `LogPanel`: badge nền tảng + viền trạng thái
- `ui/log_panel.py`: thêm class `_CommentItemDelegate(QStyledItemDelegate)`:
  `paint()` vẽ một dải màu rộng 3px bên trái mỗi item theo `status` lưu ở
  `_STATUS_ROLE` (`status_pending`/`accent`/`text_muted`/`status_error` — map
  1-1 với `ReadStatus`), và một badge nhỏ bo tròn (nền `platform_tiktok`/
  `platform_youtube`/xám cho `mock`) chứa chữ viết tắt nền tảng ("TT"/"YT"/"MK")
  ở đầu dòng, trước phần text hiện có (vẫn vẽ text bằng
  `super().paint()`/`QStyleOptionViewItem` mặc định, chỉ chèn thêm phần vẽ
  badge/viền — không tự vẽ lại toàn bộ text để không phá word-wrap/selection
  có sẵn của `QListWidget`).
  `sizeHint()` cộng thêm chiều rộng dành cho badge vào kích thước mặc định.
- `_set_status()` trong `LogPanel`: bỏ hoàn toàn phần chèn prefix emoji
  (`_STATUS_ICON`) và đổi màu chữ thủ công qua `palette()`; thay vào đó chỉ
  `item.setData(_STATUS_ROLE, status)` (giữ) + `item.setText(base_text)`
  (không prefix nữa, vì icon trạng thái giờ do delegate vẽ) + với `REMOVED`
  vẫn cần hiển thị lý do (`reason`) — nối vào cuối text thay vì đầu, ví dụ
  `f"{base_text} — {reason}"`.
  Gán `self.list_widget.setItemDelegate(_CommentItemDelegate(self.list_widget))`
  trong `__init__`.
- **Test**: `tests/test_log_panel.py` — các test hiện tại assert `item.text()`
  chứa prefix emoji (`"⏳ ..."`, `"🔊 ..."`...) hoặc `item.foreground()` theo
  màu palette cần sửa lại: prefix emoji không còn, chuyển sang assert
  `item.data(_STATUS_ROLE)` đúng `ReadStatus` (cách này thực ra đúng hơn với
  ý định gốc của test — không phụ thuộc cách hiển thị). Test `REMOVED` sửa
  assert text sang dạng `"... — <reason>"`.
- **Kiểm chứng thủ công**: script tay dựng `LogPanel` độc lập, bơm vài
  `Comment` giả (platform khác nhau) qua `queue.put()`, gọi tay
  `set_now_reading`/`set_finished_reading`/`mark_removed`, xác nhận badge +
  viền trái hiển thị đúng màu qua từng trạng thái.

## Nhánh B — Phase 4: `VoicesPage`

- `ui/voices_page.py` (mới): chuyển nguyên `_VoiceListLoader`, `_VoiceDemoWorker`,
  `_EditCloneVoiceDialog` và toàn bộ phần "Giọng đọc" của `SettingsPanel`
  (`voice_list`, `demo_text_edit`, `demo_button`, `edit_clone_button`,
  `remove_clone_button`, `clone_name_edit`, `clone_add_button`, cùng các method
  `_populate_voice_list`, `_refresh_voice_list`, `_current_voice_item`,
  `_update_voice_action_buttons`, `_on_voice_selection_changed`,
  `_on_add_clone_voice`, `_on_edit_clone_voice`, `_on_remove_clone_voice`,
  `_on_demo_clicked`, `_on_demo_finished`, `_on_demo_failed`) vào class
  `VoicesPage(QWidget)` nhận `cfg`, `voice_manager`, `audio_output` qua
  constructor (giống chữ ký cũ của `SettingsPanel`, bớt `parent` dialog).
- Đổi hành vi lưu: bỏ hẳn `save_button`/`_on_save_clicked` cho phần giọng đọc —
  `_on_voice_selection_changed` (khi `currentItemChanged`) gọi thẳng
  `self._cfg.set("selected_voice", ...)` + `self._cfg.save()` ngay khi người
  dùng chọn dòng khác trong `voice_list` (thay vì đợi bấm Lưu).
- Badge "Clone": trong `_populate_voice_list`, bỏ hậu tố text `_CLONE_SUFFIX`;
  thay bằng `item.setText(label)` bình thường + vẽ badge pill "Clone" qua một
  delegate nhỏ tương tự Phase 3 (hoặc đơn giản hơn: `QListWidgetItem` hỗ trợ
  `setData(Qt.DecorationRole, ...)`? — không đủ để làm pill; dùng
  `QStyledItemDelegate` riêng cho `voice_list`, vẽ text bình thường +
  một pill nhỏ bên phải nếu `item.data(Qt.UserRole + 1)` là `True`).
- Bọc nội dung trong `QFrame` class="card", thêm icon (`load_icon("mic-2",
  ...)`) cạnh tiêu đề.
- **Test**: `tests/test_settings_panel.py` nếu tồn tại và test phần giọng đọc
  cần đổi tên/đường dẫn import sang `voices_page.VoicesPage`; thêm case xác
  nhận chọn giọng khác gọi `cfg.set`/`cfg.save` ngay (mock `Config.save` đếm
  số lần gọi).
- **Kiểm chứng thủ công**: script tay dựng `VoicesPage` độc lập với
  `VoiceManager`/`AudioOutput` thật, chọn giọng khác nhau, đóng mở lại app
  xác nhận `selected_voice` trong `~/.cmt-speak/config.json` đã đổi ngay
  không cần thao tác Lưu nào.

## Nhánh C — Phase 5: `FilterPage`

- `ui/filter_page.py` (mới): chuyển `_SampleBlocklistDialog` và toàn bộ phần
  "Bộ lọc nội dung" của `SettingsPanel` (`blocklist_widget`,
  `blocklist_entry_edit`, `blocklist_add_button`, `blocklist_remove_button`,
  `blocklist_import_button`, `blocklist_sample_button`, `blocklist_mode_combo`,
  `dedup_mode_combo`, `dedup_window_spin`, cùng `_build_blocklist_section`,
  `_blocklist_entries`, `_add_blocklist_entries`, `_on_add_blocklist_entry`,
  `_on_remove_blocklist_entry`, `_on_import_blocklist_file`,
  `_on_show_sample_blocklist`) vào class `FilterPage(QWidget)` nhận `cfg`.
- Lưu tức thì: mỗi thao tác thay đổi danh sách (thêm/xóa/import/áp dụng từ mẫu)
  gọi luôn `self._cfg.set("blocklist", self._blocklist_entries())` +
  `self._cfg.save()` ở cuối handler tương ứng (thay vì chỉ cập nhật
  `blocklist_widget` chờ Lưu); 2 combo (`blocklist_mode`, `dedup_mode`) lưu
  ngay trong slot `currentIndexChanged`; `dedup_window_spin` lưu trong slot
  `valueChanged` (spin box không cần debounce vì không đổi liên tục như gõ
  chữ).
- Bọc 2 khối (danh sách từ cấm; cấu hình chế độ) trong 2 `QFrame` class="card"
  riêng, thêm icon (`load_icon("filter", ...)`) cạnh tiêu đề.
- **Test**: cập nhật test blocklist hiện có (nếu có trong
  `tests/test_settings_panel.py` hoặc tương đương) sang `FilterPage`; thêm
  case xác nhận thêm 1 từ cấm gọi `cfg.save()` ngay (đếm số lần gọi mock).
- **Kiểm chứng thủ công**: thêm/xóa từ cấm, import file mẫu, đổi 2 combo +
  spin box, đóng mở lại app xác nhận mọi thay đổi đã được ghi vào
  `config.json` dù không có nút Lưu nào được bấm.

## Nhánh D — Phase 6: `GeneralPage`

- `ui/general_page.py` (mới): chuyển phần "Chung" của `SettingsPanel`
  (`device_combo`, `refresh_devices_button`, `template_edit`, `api_key_edit`,
  `skip_mode_combo`) vào class `GeneralPage(QWidget)` nhận `cfg`,
  `audio_output`.
- Lưu tức thì: `device_combo`/`skip_mode_combo` lưu ngay trong
  `currentIndexChanged` (bỏ qua tín hiệu do `_refresh_device_combo` tự phát
  ra lúc nạp — dùng `blockSignals(True/False)` bao quanh như code cũ đã làm
  cho việc nạp ban đầu, chỉ khác là giờ thay đổi thật sự của người dùng phải
  lưu ngay); `template_edit`/`api_key_edit` (là `QLineEdit`, gõ liên tục) lưu
  qua `textChanged` nối với một `QTimer(singleShot=True, interval=300ms)` —
  mỗi lần gõ reset timer, hết 300ms không gõ thêm mới thật sự
  `cfg.set(...)` + `cfg.save()`, tránh ghi file mỗi phím bấm.
- Bọc trong `QFrame` class="card", thêm icon (`load_icon("settings", ...)`)
  cạnh tiêu đề.
- **Test**: thêm case cho debounce của `template_edit`/`api_key_edit` — gõ
  nhiều lần liên tiếp trong lúc timer chưa hết chỉ gọi `cfg.save()` đúng 1
  lần cuối cùng (dùng `QTest`/xử lý event loop trong test, hoặc gọi thẳng
  slot debounce mà không đợi `QTimer` thật bằng cách set `interval` rất nhỏ
  trong test hoặc trigger `timeout` thủ công).
- **Kiểm chứng thủ công**: đổi thiết bị audio, sửa template, nhập API key, đổi
  skip mode, đóng mở lại app xác nhận mọi giá trị đã lưu đúng.

## Phase 7 — Dựng `MainWindow` mới: sidebar + `QStackedWidget`, xoá `SettingsPanel`

- `ui/main_window.py`: viết lại `MainWindow.__init__`:
  - Dựng sidebar (`QWidget` rộng cố định 200px, nền `bg_sidebar`) chứa 4
    `QToolButton` checkable (`toolButtonStyle=Qt.ToolButtonTextBesideIcon`,
    property `class="nav-item"`) trong một `QButtonGroup` (exclusive) — Live
    (`radio`), Giọng đọc (`mic-2`), Bộ lọc nội dung (`filter`), Chung
    (`settings`) — cộng label version ở đáy (`QLabel("cmt-speak v{APP_VERSION}")`,
    màu `text_muted`, đẩy xuống bằng `addStretch(1)` phía trên nó).
  - Dựng `QStackedWidget` chứa: trang Live (một `QWidget` mới lắp
    `ConnectionPanel` đã restyle ở Phase 1 + `PlaybackControls` từ Phase 2 +
    `LogPanel` đã restyle ở Phase 3, theo đúng bố cục dọc cũ), `VoicesPage`,
    `FilterPage`, `GeneralPage` (từ 3 nhánh B/C/D).
  - Click nút sidebar → `stacked_widget.setCurrentIndex(...)`; trang mặc định
    Live (`index 0`).
  - Xoá `_build_menu_bar` cũ và `SettingsPanel`/`_on_open_settings`/
    `settings_dialog`; xoá file `ui/settings_panel.py` (toàn bộ nội dung đã
    chuyển sang 3 page mới ở Phase 4-6).
  - Menu tối thiểu: một `QMenu` duy nhất tên "cmt-speak" trong `menuBar()`
    chứa 2 action "Giới thiệu" (`_on_show_about`, giữ nguyên nội dung) và
    "Thoát" (`self.close`) — thay cho 3 menu "Tệp"/"Cài đặt"/"Trợ giúp" cũ.
  - `closeEvent`: bỏ dòng `self.settings_dialog.shutdown()` (không còn dialog
    riêng); nếu `VoicesPage` có `_VoiceListLoader`/`_VoiceDemoWorker` đang chạy
    nền, thêm method `VoicesPage.shutdown()` (chuyển nguyên logic từ
    `SettingsPanel.shutdown()` cũ) và gọi từ đây.
  - `__main__.py`/entry point: sau khi tạo `QApplication`, gọi
    `app.setStyleSheet(theme.STYLESHEET)` trước khi tạo `MainWindow`.
- **Test**: rà lại toàn bộ `tests/` xem còn import `SettingsPanel` ở đâu không
  (`grep -rn SettingsPanel tests/`), cập nhật hết sang page tương ứng.
- **Kiểm chứng thủ công**: `uv run python -m cmtspeak` — xác nhận: mở app vào
  thẳng trang Live; chuyển qua lại 4 mục sidebar mượt, đúng nội dung; kết nối
  TikTok/YouTube (dùng `MockConnector` nếu cần) vẫn hoạt động và status pill
  đổi màu; Tạm dừng/Bỏ qua/Xóa hàng đợi vẫn đúng hành vi cũ; đổi giọng đọc,
  thêm từ cấm, sửa template — tắt app rồi mở lại xác nhận mọi thứ được lưu
  đúng mà không cần bấm nút Lưu nào; nhấn Cmd+Q (macOS) hoặc menu "cmt-speak
  → Thoát" thoát app bình thường.

## Phase 8 — Rà soát cuối

- Chạy toàn bộ `pytest`, đảm bảo pass; `grep -rn "settings_panel\|SettingsPanel\|_STATUS_ICON\|_CLONE_SUFFIX" src/ tests/` để chắc chắn không còn tàn dư code cũ.
- Đối chiếu lại "Ngoài phạm vi" trong design doc: xác nhận không có gì trong
  `connectors/`, `tts/`, `audio/`, `queue_bus.py`, `config.py`, `models.py` bị
  đổi ngoài các thêm-key thuần túy trong `config.py` nếu có phát sinh (theo
  design, không dự kiến cần thêm key mới cho phase này).
  Xác nhận không có custom frameless window (title bar gốc OS vẫn còn).
- Test tay tổng hợp một phiên đầy đủ: mở app, kết nối 1 nền tảng thật (TikTok
  hoặc YouTube), để chạy vài phút quan sát danh sách bình luận (badge/viền
  đúng theo trạng thái thực), thử cả 4 trang sidebar trong lúc đang live,
  đóng app giữa chừng và mở lại xác nhận toàn bộ cấu hình (giọng, blocklist,
  device, template, api key, skip mode) còn nguyên.
