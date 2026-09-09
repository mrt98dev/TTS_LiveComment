from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from cmtspeak.connectors.base import (
    CONNECTED,
    CONNECTING,
    DISCONNECTED,
    ERROR,
    RECONNECTING,
    Connector,
    next_backoff_delay,
)
from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue

# Fallback poll interval (ms) if a response somehow omits pollingIntervalMillis.
_DEFAULT_POLLING_INTERVAL_MS = 5000

_SPECIAL_PATH_RE = re.compile(r"^/(?:live|embed|shorts)/([^/?#]+)")


class VideoNotLiveError(Exception):
    """Internal, never a real API exception: raised when a video can't be
    resolved to a currently-active live chat (video not found / not live /
    live chat ended, or a malformed video ID/URL). Always terminal - the
    design only wants automatic reconnect for network-ish errors, not for
    "this isn't a live stream"."""


def extract_video_id(video_id_or_url: str) -> str:
    """Accept a bare YouTube video ID or a full URL (watch?v=, youtu.be/,
    live/, embed/, shorts/ forms) and return just the video ID."""
    candidate = (video_id_or_url or "").strip()
    if not candidate:
        raise ValueError("video_id_or_url must not be empty")

    parsed = urlparse(candidate)

    # No scheme/host -> treat the whole string as a bare video ID.
    if not parsed.scheme and not parsed.netloc:
        return candidate

    netloc = parsed.netloc.lower()

    if "youtu.be" in netloc:
        video_id = parsed.path.strip("/").split("/")[0]
        if video_id:
            return video_id

    if "youtube.com" in netloc:
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            values = query.get("v")
            if values and values[0]:
                return values[0]
        match = _SPECIAL_PATH_RE.match(parsed.path)
        if match:
            return match.group(1)

    # Fallback: last non-empty path segment (best effort for unusual URLs).
    segments = [seg for seg in parsed.path.split("/") if seg]
    if segments:
        return segments[-1]

    raise ValueError(f"Could not extract a YouTube video ID from: {video_id_or_url!r}")


def _parse_published_at(published_at: str | None) -> float:
    if not published_at:
        return time.time()
    try:
        # RFC3339, e.g. "2016-08-19T22:44:34.836Z"
        return datetime.fromisoformat(published_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


def normalize_message(item: dict) -> Comment:
    """Convert one raw `liveChatMessages` resource (as returned by the
    YouTube Data API v3) into a Comment. Pure/synchronous, no network access
    required — safe to unit test with a fixture dict."""
    snippet = item.get("snippet") or {}
    author_details = item.get("authorDetails") or {}

    author = author_details.get("displayName") or "?"
    text = snippet.get("displayMessage")
    if text is None:
        # Some message types (super chat, member milestones, ...) nest the
        # text differently; fall back to the raw text message details.
        text = (snippet.get("textMessageDetails") or {}).get("messageText", "")
    ts = _parse_published_at(snippet.get("publishedAt"))

    return Comment(platform="youtube", author=author, text=text, ts=ts)


def _extract_error_reasons(exc: HttpError) -> list[str]:
    """Best-effort extraction of the structured `reason` code(s) (e.g.
    "quotaExceeded", "keyInvalid") that the YouTube API attaches to error
    responses, in addition to the free-text message."""
    reasons: list[str] = []
    details = exc.error_details
    if isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict) and detail.get("reason"):
                reasons.append(str(detail["reason"]))
    elif isinstance(details, dict) and details.get("reason"):
        reasons.append(str(details["reason"]))
    return reasons


def describe_http_error(exc: HttpError) -> str:
    """Map an HttpError from the YouTube Data API into a specific,
    human-readable status message, distinguishing at least: invalid/missing
    API key, video not live / no active live chat, and quota exceeded."""
    status = getattr(exc.resp, "status", None)
    reasons = [r.lower() for r in _extract_error_reasons(exc)]
    message_text = (exc.reason or "").lower()
    haystack = " ".join(reasons + [message_text])

    if any("quota" in r for r in reasons) or "quota" in haystack:
        return (
            "Đã vượt quota YouTube Data API (mặc định 10.000 unit/ngày). "
            "Vui lòng thử lại vào ngày hôm sau hoặc dùng API key khác."
        )

    if any(r in ("keyinvalid", "badapikey", "api_key_invalid") for r in reasons) or (
        "api key not valid" in haystack or "api key not found" in haystack
    ):
        return "YouTube API key không hợp lệ. Vui lòng kiểm tra lại API key trong Settings."

    if any(r in ("livechatnotfound", "livechatended", "livechatdisabled") for r in reasons):
        return "Live chat của video này đã kết thúc hoặc không còn hoạt động."

    if status == 403:
        return f"YouTube API từ chối yêu cầu (403): {exc.reason or 'không rõ lý do'}."
    if status == 400:
        return f"YouTube API key hoặc tham số không hợp lệ (400): {exc.reason or 'không rõ lý do'}."

    return f"Lỗi YouTube API (HTTP {status}): {exc.reason or 'không rõ lý do'}."


def is_reconnectable_error(exc: Exception) -> bool:
    """Classify a YouTubeConnector failure: True if it's worth retrying
    with backoff (network/transient-HTTP hiccup), False if retrying can
    never help. Built on the same reason/message classification
    `describe_http_error` already does, so the two stay in sync.

    Terminal (False):
      - `VideoNotLiveError`: the video isn't live / has no active live
        chat, or couldn't be resolved at all - matches the design's "live
        has genuinely ended" case exactly.
      - Invalid/missing API key: the same key will fail again immediately,
        no wait can fix it.
      - Quota exceeded: judgment call. The design's rule is "don't retry
        when it means the live has truly ended", and a quota wall is not
        that - but our backoff tops out at 30s, and no 30s wait ever
        refills a daily quota, so retrying just spends more quota against
        the same wall for no benefit. Treated as terminal, like an invalid
        key, rather than hammering the API until midnight UTC.

    Reconnectable (True):
      - Any other HttpError (403 without a specific reason, 5xx, etc.).
      - Any non-HttpError exception (client build failures, socket/timeout
        errors, ...), on the assumption that most such failures surface as
        generic exceptions rather than a classified HttpError.
    """
    if isinstance(exc, VideoNotLiveError):
        return False

    if isinstance(exc, HttpError):
        reasons = [r.lower() for r in _extract_error_reasons(exc)]
        message_text = (exc.reason or "").lower()
        haystack = " ".join(reasons + [message_text])

        if any(r in ("keyinvalid", "badapikey", "api_key_invalid") for r in reasons) or (
            "api key not valid" in haystack or "api key not found" in haystack
        ):
            return False

        if any("quota" in r for r in reasons) or "quota" in haystack:
            return False

        if any(r in ("livechatnotfound", "livechatended", "livechatdisabled") for r in reasons):
            return False

        return True

    return True


class YouTubeConnector(Connector):
    """Polls YouTube Data API v3 `liveChatMessages.list` for a manually
    supplied live video (URL or bare ID) + API key, pushing normalized
    Comments into the shared queue. Runs its own background thread so it
    never blocks the Qt event loop.

    On a failure that looks like a network/transient-HTTP hiccup
    (`is_reconnectable_error`), retries forever with increasing backoff
    (`RECONNECTING` status), re-resolving the live chat ID and resuming
    polling each time - all on this same background thread, no extra
    threads spawned. A failure that means the video genuinely isn't live
    (or an invalid API key / exhausted quota, see `is_reconnectable_error`)
    stops the connector for good instead.
    """

    def __init__(self, queue: CommentQueue, api_key: str, video_id_or_url: str) -> None:
        super().__init__(queue)
        self._api_key = api_key
        self._video_id_or_url = video_id_or_url
        # Set by stop(); checked before every (re)connect attempt and used
        # to interrupt a backoff wait (or the poll interval wait) early so
        # a manual disconnect during "reconnecting..." is honored promptly
        # instead of resurrecting a connection the user deliberately closed.
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._youtube = None
        self._reconnect_attempt = 0

    def start(self) -> None:
        self._stop_event.clear()
        self._reconnect_attempt = 0
        self.status_changed.emit(CONNECTING, "")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self.status_changed.emit(DISCONNECTED, "")

    # -- internals ---------------------------------------------------

    def _run(self) -> None:
        try:
            self._youtube = build("youtube", "v3", developerKey=self._api_key, cache_discovery=False)
        except Exception as exc:  # noqa: BLE001 - must never crash the thread
            self.status_changed.emit(ERROR, f"Không thể khởi tạo YouTube API client: {exc}")
            return

        while True:
            if self._stop_event.is_set():
                return

            exc = self._connect_and_poll_once()
            if exc is None:
                # Clean return: stop() was called mid-poll.
                return

            if not is_reconnectable_error(exc):
                self.status_changed.emit(ERROR, self._describe_error(exc))
                return

            if self._stop_event.is_set():
                return

            self._reconnect_attempt += 1
            delay = next_backoff_delay(self._reconnect_attempt)
            self.status_changed.emit(
                RECONNECTING,
                f"Mất kết nối, thử lại sau {delay:.0f}s (lần {self._reconnect_attempt})...",
            )
            # Event.wait doubles as an interruptible sleep: returns True
            # immediately if stop() sets the event mid-wait, instead of an
            # uninterruptible time.sleep(delay).
            if self._stop_event.wait(delay):
                return

    def _describe_error(self, exc: Exception) -> str:
        if isinstance(exc, VideoNotLiveError):
            return str(exc)
        if isinstance(exc, HttpError):
            return describe_http_error(exc)
        return f"Lỗi không xác định khi kết nối YouTube: {exc}"

    def _connect_and_poll_once(self) -> Exception | None:
        """Resolves the live chat ID and polls it until failure or a
        requested stop. Returns the exception on failure (for the retry
        loop above to classify), or None on a clean stop."""
        try:
            live_chat_id = self._resolve_live_chat_id()
        except Exception as exc:  # noqa: BLE001 - HttpError, VideoNotLiveError, or generic
            return exc

        self._reconnect_attempt = 0
        self.status_changed.emit(CONNECTED, "")
        return self._poll_loop(live_chat_id)

    def _resolve_live_chat_id(self) -> str:
        try:
            video_id = extract_video_id(self._video_id_or_url)
        except ValueError as exc:
            raise VideoNotLiveError(str(exc)) from exc

        response = self._youtube.videos().list(part="liveStreamingDetails", id=video_id).execute()
        items = response.get("items", [])
        if not items:
            raise VideoNotLiveError(f"Không tìm thấy video YouTube với ID '{video_id}'.")

        details = items[0].get("liveStreamingDetails") or {}
        live_chat_id = details.get("activeLiveChatId")
        if not live_chat_id:
            raise VideoNotLiveError(
                "Video này hiện không phải live hoặc không có live chat đang hoạt động."
            )
        return live_chat_id

    def _poll_loop(self, live_chat_id: str) -> Exception | None:
        page_token: str | None = None
        seen_ids: set[str] = set()

        while not self._stop_event.is_set():
            list_kwargs = {"liveChatId": live_chat_id, "part": "snippet,authorDetails"}
            if page_token:
                list_kwargs["pageToken"] = page_token

            try:
                response = self._youtube.liveChatMessages().list(**list_kwargs).execute()
            except Exception as exc:  # noqa: BLE001 - HttpError or generic; caller classifies
                return exc

            for item in response.get("items", []):
                item_id = item.get("id")
                if item_id is not None:
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                try:
                    comment = normalize_message(item)
                except Exception:  # noqa: BLE001 - never let one bad item kill the loop
                    continue
                self._queue.put(comment)

            page_token = response.get("nextPageToken") or page_token
            polling_interval_ms = response.get("pollingIntervalMillis") or _DEFAULT_POLLING_INTERVAL_MS

            if self._stop_event.wait(polling_interval_ms / 1000.0):
                return None
        return None
