from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import AgeRestrictedError, UserNotFoundError, UserOfflineError
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, LiveEndEvent

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

# Errors that mean the room genuinely isn't (and isn't about to become)
# reachable for reasons no amount of retrying can fix:
#   - UserOfflineError: the room simply isn't live right now.
#   - UserNotFoundError: the username doesn't resolve to any account.
#   - AgeRestrictedError: TikTokLive cannot access an age-restricted room
#     regardless of how many times it retries.
# Every other TikTokLiveError subclass (websocket/signing failures,
# timeouts, etc.) and every generic exception is treated as a possible
# network blip and IS reconnectable - per the design, we only give up when
# we are sure the live has genuinely ended, not merely because we don't
# recognize the error.
_TERMINAL_TIKTOK_ERRORS = (UserOfflineError, UserNotFoundError, AgeRestrictedError)


def normalize_comment_event(event: object) -> Comment:
    """Convert a raw TikTokLive `CommentEvent` into a normalized `Comment`.

    Pure and synchronous: reads only public attributes (`event.content` and
    `event.user.nickname`/`.display_id`), so it can be exercised in tests
    with a lightweight stand-in object (e.g. `types.SimpleNamespace`)
    instead of a real TikTokLive connection.
    """
    user = getattr(event, "user", None)
    author = (
        getattr(user, "nickname", None)
        or getattr(user, "nick_name", None)
        or getattr(user, "display_id", None)
        or getattr(user, "username", None)
        or "Unknown"
    )
    text = getattr(event, "content", None) or ""
    return Comment(platform="tiktok", author=str(author), text=str(text), ts=time.time())


def is_reconnectable_error(exc: Exception) -> bool:
    """Classify a TikTokLive connection failure: True if it's worth
    retrying (network/connection hiccup), False if it means the live has
    genuinely ended / is genuinely unreachable and retrying is pointless.
    See `_TERMINAL_TIKTOK_ERRORS` for the exact terminal cases."""
    return not isinstance(exc, _TERMINAL_TIKTOK_ERRORS)


class TikTokConnector(Connector):
    """Connects to a TikTok LIVE room by username via the `TikTokLive`
    library. The library's asyncio client runs on a dedicated background
    thread (with its own event loop) so it never blocks the Qt main loop.

    Connection is by manual username entry only. On disconnect / live-end /
    connection error, the connector classifies the failure
    (`is_reconnectable_error`): a genuine "not live" condition stops it for
    good, while anything that looks like a network blip is retried forever
    on the same background thread/event loop with increasing backoff
    (`RECONNECTING` status), until it either reconnects or the user calls
    `stop()`.
    """

    def __init__(self, queue: CommentQueue, username: str) -> None:
        super().__init__(queue)
        self._username = username
        self._client: Optional[TikTokLiveClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        # Set by stop(); checked before every (re)connect attempt and used
        # to interrupt a backoff wait early so a manual disconnect during
        # "reconnecting..." is honored promptly instead of resurrecting a
        # connection the user deliberately closed.
        self._stop_requested = threading.Event()
        self._reconnect_attempt = 0

    def start(self) -> None:
        self._stop_requested.clear()
        self._reconnect_attempt = 0
        self.status_changed.emit(CONNECTING, "")
        self._thread = threading.Thread(target=self._run, daemon=True, name="TikTokConnector")
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        client = self._client
        loop = self._loop
        if client is not None and loop is not None and not loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
                future.result(timeout=5)
            except Exception:
                # Best-effort: if the loop/thread already tore itself down
                # (e.g. the live ended concurrently) there is nothing left
                # to disconnect.
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        """Runs on the background thread for the connector's whole
        lifetime: attempts a connection, and on a reconnectable failure
        waits out a backoff then tries again, forever, until either a
        successful/clean disconnect happens or stop() is called. Never
        spawns extra threads and never touches the Qt thread's loop."""
        while True:
            if self._stop_requested.is_set():
                return

            exc = self._connect_once()
            if exc is None:
                # Clean return from client.connect(): either the user
                # called stop() (which itself calls client.disconnect())
                # or the library ended the session on its own without
                # raising. Either way, do not resurrect it automatically.
                return

            if not is_reconnectable_error(exc):
                self.status_changed.emit(ERROR, str(exc) or exc.__class__.__name__)
                return

            if self._stop_requested.is_set():
                return

            self._reconnect_attempt += 1
            delay = next_backoff_delay(self._reconnect_attempt)
            self.status_changed.emit(
                RECONNECTING,
                f"Mất kết nối, thử lại sau {delay:.0f}s (lần {self._reconnect_attempt})...",
            )
            # Event.wait doubles as an interruptible sleep: returns True
            # immediately if stop_requested is set mid-wait, instead of an
            # uninterruptible time.sleep(delay).
            if self._stop_requested.wait(delay):
                return

    def _connect_once(self) -> Optional[Exception]:
        """Runs a single TikTokLive connection attempt on a fresh event
        loop for this thread, blocking until it disconnects/errors.
        Returns the exception on failure (for the retry loop above to
        classify), or None on a clean return."""
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)

        client = TikTokLiveClient(unique_id=self._username)
        self._client = client

        client.on(ConnectEvent)(self._on_connect)
        client.on(CommentEvent)(self._on_comment)
        client.on(DisconnectEvent)(self._on_disconnect)
        client.on(LiveEndEvent)(self._on_live_end)

        result_exc: Optional[Exception] = None
        try:
            # process_connect_events=False: skip replaying the batch of
            # recent comments TikTok bundles into the initial room-join
            # response — those same comments are also delivered again a
            # moment later over the live WebSocket, so processing both
            # would read every early comment twice.
            loop.run_until_complete(
                client.connect(fetch_live_check=True, process_connect_events=False)
            )
        except Exception as exc:  # noqa: BLE001 - never let a connector crash the app
            # Covers TikTokLiveError subclasses (UserOfflineError, websocket
            # failures, ...) and any other library/network exception; the
            # caller classifies it via is_reconnectable_error.
            result_exc = exc
        else:
            self.status_changed.emit(DISCONNECTED, "")
        finally:
            self._loop = None
            self._client = None
            loop.close()
        return result_exc

    def _on_connect(self, _event: ConnectEvent) -> None:
        self._reconnect_attempt = 0
        self.status_changed.emit(CONNECTED, "")

    def _on_comment(self, event: CommentEvent) -> None:
        self._queue.put(normalize_comment_event(event))

    def _on_disconnect(self, _event: DisconnectEvent) -> None:
        # The websocket loop ends right after this fires, and `_run`
        # reports DISCONNECTED once `client.connect(...)` returns. Kept as
        # an explicit no-op handler in case a future TikTokLive version
        # attaches useful info (e.g. a reason) to this event.
        pass

    def _on_live_end(self, _event: LiveEndEvent) -> None:
        # Same rationale as `_on_disconnect`: the actual status_changed
        # emission happens once the connection loop unwinds in `_run`.
        pass
