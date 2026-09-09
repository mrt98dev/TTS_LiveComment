from __future__ import annotations

import time

from PySide6.QtCore import Qt
from TikTokLive.client.errors import UserNotFoundError, UserOfflineError, WebsocketURLMissingError

from cmtspeak.connectors import tiktok_connector as tiktok_connector_module
from cmtspeak.connectors.base import RECONNECTING
from cmtspeak.connectors.tiktok_connector import TikTokConnector, is_reconnectable_error
from cmtspeak.queue_bus import CommentQueue


class _FakeClient:
    """Stand-in for TikTokLive's TikTokLiveClient: records how connect() was
    called and returns immediately, no network access."""

    last_connect_kwargs: dict | None = None

    def __init__(self, unique_id: str) -> None:
        self.unique_id = unique_id

    def on(self, _event_cls):
        def decorator(fn):
            return fn

        return decorator

    async def connect(self, **kwargs):
        _FakeClient.last_connect_kwargs = kwargs


def test_start_disables_process_connect_events(monkeypatch):
    """Regression test: TikTok bundles a batch of recent comments into the
    initial room-join response, and the same comments arrive again moments
    later over the live WebSocket. Verified live against a real session
    (user chichiaoe) that this double-delivers the first several comments
    unless process_connect_events=False is passed to connect()."""
    _FakeClient.last_connect_kwargs = None
    monkeypatch.setattr(tiktok_connector_module, "TikTokLiveClient", _FakeClient)

    connector = TikTokConnector(CommentQueue(), "someuser")
    connector.start()
    connector._thread.join(timeout=2)

    assert _FakeClient.last_connect_kwargs is not None
    assert _FakeClient.last_connect_kwargs["process_connect_events"] is False


def test_is_reconnectable_error_false_for_user_offline():
    assert is_reconnectable_error(UserOfflineError()) is False


def test_is_reconnectable_error_false_for_user_not_found():
    # Also a permanent condition (bad username) - retrying won't fix it.
    assert is_reconnectable_error(UserNotFoundError("someuser")) is False


def test_is_reconnectable_error_true_for_generic_exception():
    assert is_reconnectable_error(ConnectionError("boom")) is True


def test_is_reconnectable_error_true_for_other_tiktok_live_error():
    # A websocket-layer failure is exactly the kind of network blip that
    # should be retried, unlike UserOfflineError/UserNotFoundError.
    assert is_reconnectable_error(WebsocketURLMissingError()) is True


class _FlakyClient:
    """Stand-in TikTokLiveClient: fails once with a reconnectable error,
    then "connects" and returns cleanly (simulating a graceful disconnect
    right after), so the retry loop under test terminates on its own."""

    attempts = 0

    def __init__(self, unique_id: str) -> None:
        self.unique_id = unique_id

    def on(self, _event_cls):
        def decorator(fn):
            return fn

        return decorator

    async def connect(self, **kwargs):
        _FlakyClient.attempts += 1
        if _FlakyClient.attempts == 1:
            raise ConnectionError("simulated network blip")
        return


def test_retry_loop_reconnects_after_reconnectable_error(monkeypatch):
    _FlakyClient.attempts = 0
    monkeypatch.setattr(tiktok_connector_module, "TikTokLiveClient", _FlakyClient)
    # Skip the real backoff wait so the test runs fast.
    monkeypatch.setattr(tiktok_connector_module, "next_backoff_delay", lambda attempt: 0.0)

    statuses: list[tuple[str, str]] = []
    connector = TikTokConnector(CommentQueue(), "someuser")
    # DirectConnection: the emitting background thread invokes the slot
    # in-place instead of queuing it for a Qt event loop that isn't
    # running in this test, so the assertion below sees every emission.
    connector.status_changed.connect(
        lambda status, message: statuses.append((status, message)),
        Qt.ConnectionType.DirectConnection,
    )

    connector.start()
    connector._thread.join(timeout=2)

    assert _FlakyClient.attempts == 2
    assert any(status == RECONNECTING for status, _ in statuses)


class _AlwaysFailClient:
    """Stand-in TikTokLiveClient whose connect() always raises a
    reconnectable error, used to verify stop() interrupts a backoff wait
    promptly instead of letting the retry loop keep going."""

    attempts = 0

    def __init__(self, unique_id: str) -> None:
        self.unique_id = unique_id

    def on(self, _event_cls):
        def decorator(fn):
            return fn

        return decorator

    async def connect(self, **kwargs):
        _AlwaysFailClient.attempts += 1
        raise ConnectionError("simulated network blip")


def test_stop_during_backoff_wait_halts_retries(monkeypatch):
    _AlwaysFailClient.attempts = 0
    monkeypatch.setattr(tiktok_connector_module, "TikTokLiveClient", _AlwaysFailClient)
    # A long backoff so the test can reliably catch the connector mid-wait.
    monkeypatch.setattr(tiktok_connector_module, "next_backoff_delay", lambda attempt: 5.0)

    connector = TikTokConnector(CommentQueue(), "someuser")
    connector.start()

    # Give the first (failing) attempt time to run and enter the backoff wait.
    time.sleep(0.2)
    connector.stop()  # should interrupt the 5s wait almost immediately

    assert connector._thread is None
    assert _AlwaysFailClient.attempts == 1
