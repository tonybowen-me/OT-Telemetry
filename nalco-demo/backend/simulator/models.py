from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class CommandState(BaseModel):
    pump_commanded: bool
    valve_open: bool
    bypass_open: bool
    dosing_active: bool
    mode: Literal["normal", "recirculation"]


class PrimaryReadings(BaseModel):
    flow_rate: float            # L/min  — FT-101
    tank_level: float           # %      — LT-101
    downstream_pressure: float  # bar    — PT-101
    chemical_concentration: float  # mg/L  — AT-101 (chlorine residual)


class SecondaryReadings(BaseModel):
    pump_power_draw: float          # kW     — PM-101
    downstream_conductivity: float  # µS/cm  — CT-101


class TelemetryFrame(BaseModel):
    timestamp: datetime
    tick_number: int
    operating_mode: Literal["normal", "recirculation"]
    command_state: CommandState
    primary: PrimaryReadings
    secondary: SecondaryReadings
    active_anomaly: Optional[str] = None
