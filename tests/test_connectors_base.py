from __future__ import annotations

import pytest

from cmtspeak.connectors.base import next_backoff_delay


@pytest.mark.parametrize(
    "attempt,expected",
    [
        (1, 2.0),
        (2, 5.0),
        (3, 10.0),
        (4, 30.0),
        (5, 30.0),
        (10, 30.0),
        (100, 30.0),
    ],
)
def test_next_backoff_delay_sequence(attempt: int, expected: float):
    assert next_backoff_delay(attempt) == expected
