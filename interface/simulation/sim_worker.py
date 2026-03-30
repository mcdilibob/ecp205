"""
simulation/sim_worker.py — Real-time plant simulation in a QThread.

Emits data_received with the same signature as SerialWorker so MainWindow
does not need to distinguish between hardware and simulation data.
"""

from __future__ import annotations

from math import pi, sin

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from .plant_model import PlantModel

_SIM_DT       = 0.001   # RK4 integration step (s)
_EMIT_HZ      = 100     # data emission rate — matches firmware DATA_RATE_HZ
_STEPS        = round(1.0 / (_SIM_DT * _EMIT_HZ))   # steps per emit (= 10)


class SimWorker(QThread):
    # Same signature as SerialWorker.data_received
    data_received = pyqtSignal(object, object, object, object, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model   = PlantModel(0.0024, 0.0019, 0.0019, 2.7, 2.8, 0.0, 0.0, 0.0)
        self._amp     = 1.0    # N·m  (treated same as Vq amplitude)
        self._freq    = 1.0    # Hz
        self._active  = False  # loop control flag

    # ------------------------------------------------------------------
    # Public API (called from main thread)
    # ------------------------------------------------------------------

    def set_params(
        self,
        J1: float, J2: float, J3: float,
        k1: float, k2: float,
        c1: float, c2: float, c3: float,
    ) -> None:
        self._model.set_params(J1, J2, J3, k1, k2, c1, c2, c3)

    def set_excitation(self, amp: float, freq: float) -> None:
        self._amp  = amp
        self._freq = freq

    def start_sim(self) -> None:
        self._model.reset()
        self._t_sim  = 0.0
        self._active = True
        if not self.isRunning():
            self.start()

    def stop_sim(self) -> None:
        self._active = False   # run() exits on next iteration

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self) -> None:
        dt_emit_ms = int(round(_STEPS * _SIM_DT * 1000))   # ms to sleep per emit

        while self._active:
            omega = 2.0 * pi * self._freq

            t_arr  = np.empty(_STEPS)
            a1_arr = np.empty(_STEPS)
            a2_arr = np.empty(_STEPS)
            a3_arr = np.empty(_STEPS)
            vq_arr = np.empty(_STEPS)

            for i in range(_STEPS):
                tau = self._amp * sin(omega * self._t_sim)
                a1, a2, a3 = self._model.step(tau)
                t_arr[i]  = self._t_sim * 1000.0   # ms
                a1_arr[i] = a1
                a2_arr[i] = a2
                a3_arr[i] = a3
                vq_arr[i] = tau
                self._t_sim += _SIM_DT

            self.data_received.emit(t_arr, a1_arr, a2_arr, a3_arr, vq_arr)
            self.msleep(dt_emit_ms)
