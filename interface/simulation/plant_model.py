"""
simulation/plant_model.py — 3-DOF torsional plant (ECP205).

Equations of motion (slide 7 / slide 12 of thesis):
    J1*θ̈1 + c1*θ̇1 + k1*(θ1 - θ2)            = τ
    J2*θ̈2 + c2*θ̇2 + k1*(θ2 - θ1) + k2*(θ2 - θ3) = 0
    J3*θ̈3 + c3*θ̇3 + k2*(θ3 - θ2)            = 0

State:  x = [θ1, θ̇1, θ2, θ̇2, θ3, θ̇3]
Input:  τ  (motor torque, N·m)
Output: (θ1, θ2, θ3) wrapped to [-π, π]
"""

from __future__ import annotations

from math import pi

import numpy as np


class PlantModel:
    def __init__(
        self,
        J1: float, J2: float, J3: float,
        k1: float, k2: float,
        c1: float, c2: float, c3: float,
        dt: float = 0.001,
    ) -> None:
        self._dt = dt
        self._x  = np.zeros(6)
        self._build(J1, J2, J3, k1, k2, c1, c2, c3)

    # ------------------------------------------------------------------

    def set_params(
        self,
        J1: float, J2: float, J3: float,
        k1: float, k2: float,
        c1: float, c2: float, c3: float,
    ) -> None:
        self._build(J1, J2, J3, k1, k2, c1, c2, c3)

    def reset(self) -> None:
        self._x[:] = 0.0

    # ------------------------------------------------------------------

    def _build(self, J1, J2, J3, k1, k2, c1, c2, c3) -> None:
        self._A = np.array([
            [0,          1,            0,          0,        0,       0],
            [-k1/J1, -c1/J1,       k1/J1,          0,        0,       0],
            [0,          0,            0,          1,        0,       0],
            [k1/J2,      0, -(k1+k2)/J2,      -c2/J2,  k2/J2,       0],
            [0,          0,            0,          0,        0,       1],
            [0,          0,        k2/J3,          0,  -k2/J3, -c3/J3],
        ], dtype=np.float64)
        self._B = np.array([0, 1/J1, 0, 0, 0, 0], dtype=np.float64)

    def step(self, tau: float) -> tuple[float, float, float]:
        """Advance one dt step with torque input tau. Returns (θ1, θ2, θ3) in [-π, π]."""
        h = self._dt
        Bu = self._B * tau
        k1 = self._A @ self._x + Bu
        k2 = self._A @ (self._x + h / 2 * k1) + Bu
        k3 = self._A @ (self._x + h / 2 * k2) + Bu
        k4 = self._A @ (self._x + h * k3) + Bu
        self._x += h / 6 * (k1 + 2*k2 + 2*k3 + k4)

        # wrap angles to [-π, π]
        a1 = self._x[0]
        a2 = self._x[2]
        a3 = self._x[4]
        return [a1, a2, a3]
