"""
crowd_simulator.py — Real-Time Crowd Data Simulator
Generates realistic crowd metrics for all 10 ghats, simulating
actual sensor + camera data that would come from the deployed system.
"""

import numpy as np
import math
import random
import threading
import time
from datetime import datetime
from collections import deque


class GhatSimulator:
    """Simulates real-time crowd data for a single ghat."""

    def __init__(self, ghat_idx, ghat_name, base_density=2.0, volatility=0.3):
        self.ghat_idx = ghat_idx
        self.ghat_name = ghat_name
        self.base_density = base_density
        self.volatility = volatility

        # State
        self.density = base_density
        self.inflow = int(base_density * 11000)
        self.outflow = int(self.inflow * 0.92)
        self.temp = random.uniform(28, 38)
        self.rain = 0
        self.camera_count = random.randint(30, 65)
        self.cameras_online = self.camera_count
        self.person_count = int(self.density * 150)
        self.incident_active = False
        self.incident_countdown = 0

        # History for time-series
        self.density_history = deque(maxlen=60)
        self.inflow_history = deque(maxlen=60)

        # Simulated drift direction for realistic movement
        self._drift = 0.0
        self._drift_steps = 0

    def _time_factor(self):
        """Peak hours: 5-10am and 4-8pm (higher crowds at ghats)."""
        hour = datetime.now().hour + datetime.now().minute / 60
        peak1 = math.exp(-((hour - 7.0) ** 2) / 6)
        peak2 = math.exp(-((hour - 17.5) ** 2) / 8)
        return 0.4 + (peak1 + peak2) * 0.8

    def update(self, force_incident=False):
        """Advance simulation by one tick."""
        tf = self._time_factor()

        # Drift: momentum-based random walk
        if self._drift_steps <= 0:
            self._drift = random.gauss(0, 0.15)
            self._drift_steps = random.randint(5, 20)
        self._drift_steps -= 1

        # Core density update with drift + time factor + noise
        noise = random.gauss(0, self.volatility * 0.4)
        target = self.base_density * tf
        self.density += (target - self.density) * 0.05 + self._drift + noise
        self.density = max(0.3, min(9.9, self.density))

        # Simulate incident (density spike)
        if force_incident or (random.random() < 0.002 and not self.incident_active):
            self.incident_active = True
            self.incident_countdown = random.randint(10, 30)

        if self.incident_active:
            self.density = min(9.9, self.density + 0.5)
            self.incident_countdown -= 1
            if self.incident_countdown <= 0:
                self.incident_active = False

        # Inflow/outflow based on density
        inflow_base = self.density * 12500
        self.inflow = int(inflow_base * (1 + random.gauss(0, 0.08)))
        outflow_factor = 0.85 if self.density > 5 else (0.95 if self.density > 3 else 1.02)
        self.outflow = int(self.inflow * outflow_factor + random.gauss(0, 1000))
        self.outflow = max(0, self.outflow)

        # Temperature slow drift
        self.temp += random.gauss(0, 0.05)
        self.temp = max(25, min(44, self.temp))

        # Camera failures (rare)
        online_change = random.choices([-1, 0, 0, 0, 0, 1], k=1)[0]
        self.cameras_online = max(
            int(self.camera_count * 0.85),
            min(self.camera_count, self.cameras_online + online_change)
        )

        self.person_count = int(self.density * 150 + random.gauss(0, 20))

        # Store history
        self.density_history.append(round(self.density, 3))
        self.inflow_history.append(self.inflow)

        return self.snapshot()

    def snapshot(self):
        return {
            "ghat_idx":       self.ghat_idx,
            "ghat_name":      self.ghat_name,
            "density":        round(self.density, 2),
            "inflow":         self.inflow,
            "outflow":        self.outflow,
            "net_flow":       self.inflow - self.outflow,
            "temp":           round(self.temp, 1),
            "rain":           self.rain,
            "camera_count":   self.camera_count,
            "cameras_online": self.cameras_online,
            "person_count":   self.person_count,
            "incident_active": self.incident_active,
            "density_history":  list(self.density_history),
            "timestamp":      datetime.now().isoformat(),
        }


class CrowdSimulationEngine:
    """
    Master simulation engine running all 10 ghats simultaneously
    in a background thread, providing real-time snapshot data.
    """

    GHAT_CONFIG = [
        # (name, base_density, volatility)
        ("Pushkar Ghat 1",        2.5, 0.35),
        ("Pushkar Ghat 2",        3.8, 0.45),
        ("Pushkar Ghat 3",        5.2, 0.60),   # busy ghat — higher base
        ("Kotipalli Ghat",        2.1, 0.30),
        ("Dhavaleswaram Ghat",    4.2, 0.50),
        ("Rajahmundry Main Ghat", 3.5, 0.40),
        ("Boat Club Area",        1.8, 0.25),
        ("Lanka Ghat",            4.8, 0.55),   # second busy
        ("Godavari Ardam Ghat",   2.8, 0.38),
        ("Havelock Bridge Ghat",  2.0, 0.28),
    ]

    def __init__(self, tick_interval=2.0):
        self.tick_interval = tick_interval
        self.ghats = [
            GhatSimulator(i, name, base, vol)
            for i, (name, base, vol) in enumerate(self.GHAT_CONFIG)
        ]
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._snapshots = {}
        self._tick_count = 0
        self._event_log = deque(maxlen=500)

        # Initialize
        for g in self.ghats:
            snap = g.update()
            self._snapshots[g.ghat_name] = snap

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"[SIM] Crowd simulation engine started — {len(self.ghats)} ghats, tick={self.tick_interval}s")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            start = time.time()
            for g in self.ghats:
                snap = g.update()
                with self._lock:
                    self._snapshots[g.ghat_name] = snap
                    if snap["incident_active"]:
                        self._event_log.append({
                            "type": "INCIDENT",
                            "ghat": g.ghat_name,
                            "density": snap["density"],
                            "timestamp": snap["timestamp"],
                        })
            self._tick_count += 1
            elapsed = time.time() - start
            time.sleep(max(0, self.tick_interval - elapsed))

    def get_all_snapshots(self):
        with self._lock:
            return dict(self._snapshots)

    def get_ghat_snapshot(self, ghat_name):
        with self._lock:
            return self._snapshots.get(ghat_name)

    def force_incident(self, ghat_name):
        """Trigger an emergency scenario for demo/testing."""
        for g in self.ghats:
            if g.ghat_name == ghat_name:
                g.update(force_incident=True)
                return True
        return False

    def get_system_totals(self):
        snaps = self.get_all_snapshots()
        total_persons = sum(s["person_count"] for s in snaps.values())
        total_inflow  = sum(s["inflow"] for s in snaps.values())
        total_outflow = sum(s["outflow"] for s in snaps.values())
        max_density   = max(s["density"] for s in snaps.values())
        avg_density   = sum(s["density"] for s in snaps.values()) / max(len(snaps), 1)
        cameras_total  = sum(s["camera_count"] for s in snaps.values())
        cameras_online = sum(s["cameras_online"] for s in snaps.values())
        incidents_active = sum(1 for s in snaps.values() if s["incident_active"])

        return {
            "total_persons":    total_persons,
            "total_inflow_hr":  total_inflow,
            "total_outflow_hr": total_outflow,
            "max_density":      round(max_density, 2),
            "avg_density":      round(avg_density, 2),
            "cameras_total":    cameras_total,
            "cameras_online":   cameras_online,
            "cameras_offline":  cameras_total - cameras_online,
            "incidents_active": incidents_active,
            "tick":             self._tick_count,
            "timestamp":        datetime.now().isoformat(),
        }

    def generate_camera_frames(self, ghat_idx, num_cameras=5):
        """Generate simulated camera frame metadata for a given ghat."""
        ghat = self.ghats[ghat_idx]
        snap = ghat.snapshot()
        frames = []
        for cam_i in range(num_cameras):
            frames.append({
                "camera_id":  f"CAM-{ghat_idx:02d}-{cam_i:03d}",
                "ghat_idx":   ghat_idx,
                "ghat_name":  snap["ghat_name"],
                "online":     cam_i < snap["cameras_online"],
                "person_count": max(0, int(snap["person_count"] / 5 + random.gauss(0, 10))),
                "density":    snap["density"] + random.gauss(0, 0.3),
                "area_m2":    random.uniform(80, 180),
                "has_unattended_object": random.random() < 0.03,
                "has_reverse_flow":      snap["density"] > 7 and random.random() < 0.3,
                "timestamp":  snap["timestamp"],
            })
        return frames
