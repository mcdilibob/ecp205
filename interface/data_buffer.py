"""
data_buffer.py — Circular buffer for ECP205 measurement data.

Stores the last `max_seconds` of data as numpy arrays and provides
CSV export via pandas.

Fields per sample:
    t_ms  : uint32  timestamp in milliseconds (from MCU)
    a1    : float32 disk 1 angle (radians)
    a2    : float32 disk 2 angle (radians)
    a3    : float32 disk 3 angle (radians)
    vq    : float32 motor voltage command (V)
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd


class DataBuffer:
    COLUMNS = ("t_ms", "angle_disk1_rad", "angle_disk2_rad", "angle_disk3_rad", "vq_V")

    def __init__(self, max_seconds: float = 60.0, sample_rate_hz: float = 200.0) -> None:
        max_len = int(max_seconds * sample_rate_hz)
        self._buf: deque[tuple[float, float, float, float, float]] = deque(maxlen=max_len)

    def append(self, t_ms: float, a1: float, a2: float, a3: float, vq: float) -> None:
        self._buf.append((t_ms, a1, a2, a3, vq))

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)

    # -------------------------------------------------------------------------
    # Access helpers — return numpy arrays (copies)
    # -------------------------------------------------------------------------

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (t_ms, a1, a2, a3, vq) as float64 numpy arrays."""
        if not self._buf:
            empty = np.empty(0, dtype=np.float64)
            return empty, empty, empty, empty, empty
        data = np.asarray(self._buf, dtype=np.float64)
        return data[:, 0], data[:, 1], data[:, 2], data[:, 3], data[:, 4]

    def last_n_seconds(self, n: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return arrays containing only the last `n` seconds of data."""
        t_ms, a1, a2, a3, vq = self.as_arrays()
        if t_ms.size == 0:
            return t_ms, a1, a2, a3, vq
        cutoff = t_ms[-1] - n * 1000.0
        mask = t_ms >= cutoff
        return t_ms[mask], a1[mask], a2[mask], a3[mask], vq[mask]

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def export_csv(self, path: str | Path) -> None:
        """Write full buffer to a CSV file.

        Adds a `t_s` column (seconds from first sample) for convenience.
        """
        t_ms, a1, a2, a3, vq = self.as_arrays()
        if t_ms.size == 0:
            raise ValueError("Buffer is empty — nothing to export.")

        t_s = (t_ms - t_ms[0]) / 1000.0
        df = pd.DataFrame(
            {
                "t_ms": t_ms.astype(np.uint32),
                "t_s": t_s,
                self.COLUMNS[1]: a1,
                self.COLUMNS[2]: a2,
                self.COLUMNS[3]: a3,
                self.COLUMNS[4]: vq,
            }
        )
        df.to_csv(path, index=False)
