"""
data_buffer.py — Pre-allocated numpy ring buffer for ECP205 measurement data.

Uses a fixed-size numpy array with a write-head pointer instead of a deque of
tuples, so as_arrays() is O(1) (no per-sample Python allocations) and
last_n_seconds() costs only one boolean mask operation.

Fields per sample:
    t_ms  : uint32  timestamp in milliseconds (from MCU)
    a1    : float32 disk 1 angle (radians)
    a2    : float32 disk 2 angle (radians)
    a3    : float32 disk 3 angle (radians)
    vq    : float32 motor voltage command (V)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_N_COLS = 5   # t_ms, a1, a2, a3, vq


class DataBuffer:
    COLUMNS = ("t_ms", "angle_disk1_rad", "angle_disk2_rad", "angle_disk3_rad", "vq_V")

    def __init__(self, max_seconds: float = 60.0, sample_rate_hz: float = 200.0) -> None:
        cap = int(max_seconds * sample_rate_hz)
        self._buf  = np.empty((cap, _N_COLS), dtype=np.float64)
        self._cap  = cap
        self._head = 0   # next write position
        self._size = 0   # number of valid samples

    def append(self, t_ms: float, a1: float, a2: float, a3: float, vq: float) -> None:
        self._buf[self._head] = (t_ms, a1, a2, a3, vq)
        self._head = (self._head + 1) % self._cap
        if self._size < self._cap:
            self._size += 1

    def append_batch(
        self,
        t_ms: np.ndarray,
        a1: np.ndarray,
        a2: np.ndarray,
        a3: np.ndarray,
        vq: np.ndarray,
    ) -> None:
        """Write a batch of samples in one go (avoids per-sample Python overhead)."""
        n = len(t_ms)
        for i in range(n):
            self._buf[self._head] = (t_ms[i], a1[i], a2[i], a3[i], vq[i])
            self._head = (self._head + 1) % self._cap
        self._size = min(self._size + n, self._cap)

    def clear(self) -> None:
        self._head = 0
        self._size = 0

    def __len__(self) -> int:
        return self._size

    # -------------------------------------------------------------------------
    # Access helpers — return numpy array views / slices (no full copy)
    # -------------------------------------------------------------------------

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (t_ms, a1, a2, a3, vq) in chronological order."""
        if self._size == 0:
            empty = np.empty(0, dtype=np.float64)
            return empty, empty, empty, empty, empty
        if self._size < self._cap:
            # Buffer not yet full: data is in [0 .. _head)
            d = self._buf[:self._size]
        else:
            # Buffer full: oldest sample is at _head, wrap around
            d = np.roll(self._buf, -self._head, axis=0)
        return d[:, 0], d[:, 1], d[:, 2], d[:, 3], d[:, 4]

    def last_n_seconds(
        self, n: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        t_ms, a1, a2, a3, vq = self.as_arrays()
        if t_ms.size == 0:
            return t_ms, a1, a2, a3, vq
        mask = t_ms >= (t_ms[-1] - n * 1000.0)
        return t_ms[mask], a1[mask], a2[mask], a3[mask], vq[mask]

    # -------------------------------------------------------------------------

    def export_csv(self, path: str | Path) -> None:
        t_ms, a1, a2, a3, vq = self.as_arrays()
        if t_ms.size == 0:
            raise ValueError("Buffer is empty — nothing to export.")
        t_s = (t_ms - t_ms[0]) / 1000.0
        df = pd.DataFrame({
            "t_ms":          t_ms.astype(np.uint32),
            "t_s":           t_s,
            self.COLUMNS[1]: a1,
            self.COLUMNS[2]: a2,
            self.COLUMNS[3]: a3,
            self.COLUMNS[4]: vq,
        })
        df.to_csv(path, index=False)
