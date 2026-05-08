import random

# Gaussian noise sigma per instrument tag.
# Values reflect realistic sensor accuracy for each instrument class.
_NOISE: dict[str, float] = {
    "flow_rate":               1.5,   # L/min  — ±2% at 95 L/min (electromagnetic flowmeter)
    "tank_level":              0.2,   # %       — ultrasonic level transmitter
    "downstream_pressure":     0.04,  # bar     — pressure transducer (±0.1%)
    "chemical_concentration":  0.03,  # mg/L    — online chlorine analyser
    "pump_power_draw":         0.04,  # kW      — power meter
    "downstream_conductivity": 3.0,   # µS/cm   — conductivity probe
}


def noisy(value: float, tag: str) -> float:
    """Return value perturbed by Gaussian noise appropriate for the sensor."""
    sigma = _NOISE.get(tag, 0.01)
    return value + random.gauss(0, sigma)
