"""Realistic (but SIMULATED) agricultural sensor readings.

Physics-inspired model per device:
  * temperature  - daily sine cycle (peak ~15:00) + per-device offset + noise
  * humidity     - inversely related to temperature + noise
  * soil moisture- slowly evaporates (faster when hot); an "irrigation event"
                   tops it up when it falls below a threshold

`time_scale` compresses the day so trends are visible in a short demo
(time_scale=720 -> one simulated day every 2 real minutes).
Passing a seed makes every device's sequence fully reproducible.
"""
from __future__ import annotations

import math
import random


class AgriSensorModel:
    def __init__(self, device_id: str, seed: int | None = None, time_scale: float = 720.0):
        # String seeds are hashed deterministically, so (seed, device_id) -> same data every run
        self.rng = random.Random(f"{seed}:{device_id}") if seed is not None else random.Random()
        self.time_scale = time_scale
        self.base_temp = self.rng.uniform(22.0, 29.0)
        self.temp_amplitude = self.rng.uniform(4.0, 7.0)
        self.soil = self.rng.uniform(40.0, 65.0)
        self.irrigation_threshold = self.rng.uniform(22.0, 30.0)
        self._last_sim_t: float | None = None

    def read(self, real_t: float) -> dict[str, float]:
        sim_t = real_t * self.time_scale
        hour = (sim_t / 3600.0) % 24.0

        temp = self.base_temp + self.temp_amplitude * math.sin(2 * math.pi * (hour - 9.0) / 24.0)
        temp += self.rng.gauss(0, 0.3)

        humidity = 90.0 - 1.8 * (temp - 18.0) + self.rng.gauss(0, 1.5)
        humidity = min(max(humidity, 15.0), 100.0)

        if self._last_sim_t is not None:
            dt_hours = max(sim_t - self._last_sim_t, 0.0) / 3600.0
            evaporation = 0.25 + 0.04 * max(temp - 15.0, 0.0)  # % per simulated hour
            self.soil -= evaporation * dt_hours
        self._last_sim_t = sim_t
        if self.soil < self.irrigation_threshold:
            self.soil += self.rng.uniform(25.0, 35.0)
        self.soil = min(max(self.soil + self.rng.gauss(0, 0.2), 0.0), 100.0)

        return {
            "temperature_c": round(temp, 2),
            "humidity_pct": round(humidity, 2),
            "soil_moisture_pct": round(self.soil, 2),
        }
