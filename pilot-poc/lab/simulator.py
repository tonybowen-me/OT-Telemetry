"""Live Minitown water utility: streams the DHALSIM physical process in real time.

This is the *lab* (application #1) -- a standalone OT process, independent of the
PILOT app. It advances a clock over the pre-baked EPANET/WNTR trajectory (see
``build_trajectories.py``), so at any moment there is a genuine physical state
("ground truth"). It then produces the SCADA-visible view a PLC/historian would
report, after applying whatever network attack the attacker console has armed.

The attacks reproduce DHALSIM's ``network_attacks`` semantics at the application
layer (DHALSIM does it on the wire via ARP-poison + nfqueue; the falsification is
identical):

  * concealment_mitm : freeze/replay the tank-level (and its pressure) tags at the
                       value seen when the attack was armed, so SCADA never sees
                       the tank draining -- DHALSIM ``concealment_mitm`` /
                       ``payload_replay``. The independent tank-inflow meter is
                       NOT compromised and keeps telling the truth.
  * dos              : drop the tank-level / inflow tags entirely (missing data) --
                       DHALSIM ``simple_dos_attack``.

Only ``scada_frame()`` is exposed to the outside world (that is what the PILOT app
consumes). ``truth_frame()`` exists for the utility's own HMI overlay and is never
sent to PILOT.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
TRAJECTORY_PATH = HERE / "data" / "trajectory.json"

Condition = str  # "normal" | "surge"
Attack = str     # "none" | "concealment_mitm" | "dos"

VALID_CONDITIONS = ("normal", "surge")
VALID_ATTACKS = ("none", "concealment_mitm", "dos")


class Utility:
    """Thread-safe, continuously-running Minitown SCADA process."""

    def __init__(self, tick_seconds: float = 1.2, history: int = 96):
        with TRAJECTORY_PATH.open() as f:
            self._traj = json.load(f)
        self._fields = self._traj["fields"]
        self._n = len(self._traj["conditions"]["normal"]["iteration"])
        self.step_seconds = int(self._traj["step_seconds"])
        self.tank_max_level = float(self._traj["tank_max_level"])
        self.tick_seconds = tick_seconds

        self._lock = threading.RLock()
        self._i = 0
        self._step = 0                       # monotonic stream index (never resets)
        self.condition: Condition = "normal"
        self.attack: Attack = "none"
        # Snapshot of the tags the attacker replays while concealment is armed.
        self._conceal_snapshot: Optional[dict] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._scada_hist: deque = deque(maxlen=history)
        self._truth_hist: deque = deque(maxlen=history)
        self._record()

    # --- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def advance(self) -> None:
        """Advance the process one step and record the resulting frames."""
        with self._lock:
            self._i = (self._i + 1) % self._n
            self._step += 1
            self._record()

    def _loop(self) -> None:
        while self._running:
            self.advance()
            time.sleep(self.tick_seconds)

    # --- controls (attacker / operator console) -------------------------------
    def set_condition(self, condition: Condition) -> None:
        if condition not in VALID_CONDITIONS:
            raise ValueError(f"unknown condition {condition!r}")
        with self._lock:
            self.condition = condition

    def set_attack(self, attack: Attack) -> None:
        if attack not in VALID_ATTACKS:
            raise ValueError(f"unknown attack {attack!r}")
        with self._lock:
            self.attack = attack
            if attack == "concealment_mitm":
                # Replay a healthy, in-band snapshot so SCADA sees a normal plant
                # regardless of the real state (DHALSIM concealment feeds coherent
                # replayed values). We source it from the NOMINAL trajectory at the
                # current index so the level/pressures look like business-as-usual;
                # the independent tank-inflow meter is NOT faked and keeps telling
                # the truth, which is what betrays the lie to PILOT.
                nominal = {f: self._traj["conditions"]["normal"][f][self._i]
                           for f in self._fields}
                self._conceal_snapshot = {
                    "tank_level": nominal["tank_level"],
                    "pressure_J39": nominal["pressure_J39"],
                    "pressure_J156": nominal["pressure_J156"],
                    "pressure_J280": nominal["pressure_J280"],
                }
            else:
                self._conceal_snapshot = None

    # --- physical state -------------------------------------------------------
    def _truth_at(self, i: int) -> dict:
        cols = self._traj["conditions"][self.condition]
        return {f: cols[f][i] for f in self._fields}

    def _apply_attack(self, truth: dict) -> dict:
        """Transform the honest reading into the SCADA-visible view."""
        fr = dict(truth)
        fr["attack_flag"] = 0
        fr["missing"] = 0
        if self.attack == "concealment_mitm" and self._conceal_snapshot:
            fr.update(self._conceal_snapshot)
            fr["attack_flag"] = 1
        elif self.attack == "dos":
            fr["tank_level"] = None
            fr["tank_inflow"] = None
            fr["missing"] = 1
            fr["attack_flag"] = 1
        return fr

    def _record(self) -> None:
        """Append the current honest + SCADA-reported frames to history."""
        truth = self._truth_at(self._i)
        # Monotonic stream index + wall-clock timestamp keep consecutive samples
        # exactly one step apart even across a trajectory loop boundary, so the
        # PILOT mass-balance math stays valid.
        truth["iteration"] = self._step
        truth["timestamp"] = self._step * self.step_seconds
        truth["condition"] = self.condition
        truth["attack"] = self.attack
        reported = self._apply_attack(truth)
        reported["condition"] = self.condition
        reported["attack"] = self.attack
        self._truth_hist.append(truth)
        self._scada_hist.append(reported)

    def truth_frame(self) -> dict:
        with self._lock:
            return dict(self._truth_hist[-1])

    def scada_frame(self) -> dict:
        """What SCADA / a historian reports -- after any armed attack."""
        with self._lock:
            return dict(self._scada_hist[-1])

    def scada_window(self, n: int) -> list[dict]:
        with self._lock:
            items = list(self._scada_hist)
        return [dict(x) for x in items[-n:]]

    def truth_window(self, n: int) -> list[dict]:
        with self._lock:
            items = list(self._truth_hist)
        return [dict(x) for x in items[-n:]]

    def status(self) -> dict:
        with self._lock:
            return {
                "condition": self.condition,
                "attack": self.attack,
                "iteration": self._i,
                "stream_index": self._step,
                "steps": self._n,
                "step_seconds": self.step_seconds,
                "tank_max_level": self.tank_max_level,
                "running": self._running,
                "tick_seconds": self.tick_seconds,
            }
