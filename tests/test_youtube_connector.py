from __future__ import annotations

import json
import time
from types import SimpleNamespace

from googleapiclient.errors import HttpError
from PySide6.QtCore import Qt

from cmtspeak.connectors import youtube_connector as youtube_connector_module
from cmtspeak.connectors.base import ERROR, RECONNECTING
from cmtspeak.connectors.youtube_connector import (
    VideoNotLiveError,
    YouTubeConnector,
    is_reconnectable_error,
)
from cmtspeak.queue_bus import CommentQueue


def _make_http_error(status: int, reason_code: str, message: str) -> HttpError:
    """Build a real `HttpError` carrying a structured `reason` code, the
    same shape the YouTube Data API actually returns (and the shape
    `describe_http_error`/`is_reconnectable_error` parse via
    `_extract_error_reasons`)."""
    body = {
        "error": {
            "code": status,
            "message": message,
            "errors": [{"reason": reason_code, "message": message}],
        }
    }
    resp = SimpleNamespace(status=status, reason=message)
    return HttpError(resp, json.dumps(body).encode("utf-8"))


def test_is_reconnectable_error_false_for_video_not_live():
    exc = VideoNotLiveError("Video này hiện không phải live hoặc không có live chat đang hoạt động.")
    assert is_reconnectable_error(exc) is False


def test_is_reconnectable_error_false_for_live_chat_ended():
    exc = _make_http_error(403, "liveChatEnded", "The live chat is no longer live.")
    assert is_reconnectable_error(exc) is False


def test_is_reconnectable_error_false_for_invalid_api_key():
    exc = _make_http_error(400, "keyInvalid", "API key not valid. Please pass a valid API key.")
    assert is_reconnectable_error(exc) is False


def test_is_reconnectable_error_false_for_quota_exceeded():
    # Judgment call documented in youtube_connector.is_reconnectable_error:
    # a 30s-cap backoff can never refill a daily quota, so retrying just
    # spends more quota against the same wall - treated as terminal.
    exc = _make_http_error(
        403, "quotaExceeded", "The request cannot be completed because you have exceeded your quota."
    )
    assert is_reconnectable_error(exc) is False


def test_is_reconnectable_error_true_for_generic_http_error():
    exc = _make_http_error(500, "backendError", "Internal error encountered.")
    assert is_reconnectable_error(exc) is True


def test_is_reconnectable_error_true_for_generic_exception():
    assert is_reconnectable_error(ConnectionError("network hiccup")) is True


class _FlakyYouTube:
    """Stand-in for the `googleapiclient` youtube resource: `videos().list()`
    always resolves a live chat id, `liveChatMessages().list()` fails once
    with a reconnectable HttpError then returns an empty, terminating
    response so the retry loop under test finishes on its own."""

    list_attempts = 0

    class _Videos:
        def list(self, **kwargs):
            return self

        def execute(self):
            return {"items": [{"liveStreamingDetails": {"activeLiveChatId": "chat123"}}]}

    class _LiveChatMessages:
        def list(self, **kwargs):
            return self

        def execute(self):
            _FlakyYouTube.list_attempts += 1
            if _FlakyYouTube.list_attempts == 1:
                raise _make_http_error(500, "backendError", "temporary backend error")
            return {"items": [], "pollingIntervalMillis": 1}

    def videos(self):
        return self._Videos()

    def liveChatMessages(self):
        return self._LiveChatMessages()


def test_run_retries_after_reconnectable_http_error(monkeypatch):
    _FlakyYouTube.list_attempts = 0
    monkeypatch.setattr(youtube_connector_module, "build", lambda *a, **k: _FlakyYouTube())
    monkeypatch.setattr(youtube_connector_module, "next_backoff_delay", lambda attempt: 0.0)

    statuses: list[tuple[str, str]] = []
    connector = YouTubeConnector(CommentQueue(), "fake-key", "XXXX")
    # DirectConnection: the emitting background thread invokes the slot
    # in-place instead of queuing it for a Qt event loop that isn't
    # running in this test, so the assertion below sees every emission.
    connector.status_changed.connect(
        lambda status, message: statuses.append((status, message)),
        Qt.ConnectionType.DirectConnection,
    )

    connector.start()
    time.sleep(0.3)
    connector.stop()

    assert _FlakyYouTube.list_attempts >= 2
    assert any(status == RECONNECTING for status, _ in statuses)


class _AlwaysFailYouTube:
    """videos().list() always raises a reconnectable HttpError, used to
    verify stop() interrupts a backoff wait promptly."""

    attempts = 0

    class _Videos:
        def list(self, **kwargs):
            return self

        def execute(self):
            _AlwaysFailYouTube.attempts += 1
            raise _make_http_error(500, "backendError", "temporary backend error")

    def videos(self):
        return self._Videos()


def test_stop_during_backoff_wait_halts_retries(monkeypatch):
    _AlwaysFailYouTube.attempts = 0
    monkeypatch.setattr(youtube_connector_module, "build", lambda *a, **k: _AlwaysFailYouTube())
    monkeypatch.setattr(youtube_connector_module, "next_backoff_delay", lambda attempt: 5.0)

    connector = YouTubeConnector(CommentQueue(), "fake-key", "XXXX")
    connector.start()

    time.sleep(0.3)
    connector.stop()  # should interrupt the 5s wait almost immediately

    # Note: unlike TikTokConnector, YouTubeConnector.stop() (pre-existing
    # code, not part of this change) does not reset self._thread to None -
    # check liveness instead.
    assert not connector._thread.is_alive()
    assert _AlwaysFailYouTube.attempts == 1


def test_run_stops_without_retry_on_video_not_live(monkeypatch):
    class _NotLiveYouTube:
        class _Videos:
            def list(self, **kwargs):
                return self

            def execute(self):
                return {"items": []}

        def videos(self):
            return self._Videos()

    monkeypatch.setattr(youtube_connector_module, "build", lambda *a, **k: _NotLiveYouTube())

    statuses: list[tuple[str, str]] = []
    connector = YouTubeConnector(CommentQueue(), "fake-key", "XXXX")
    connector.status_changed.connect(
        lambda status, message: statuses.append((status, message)),
        Qt.ConnectionType.DirectConnection,
    )

    connector.start()
    connector._thread.join(timeout=2)

    assert statuses[-1][0] == ERROR
    assert not any(status == RECONNECTING for status, _ in statuses)
