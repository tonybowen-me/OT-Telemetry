"""Smoke test for the simulator. Run from backend/: python test_sim.py"""
from simulator import WaterTreatmentPlant


def row(frame):
    p = frame.primary
    s = frame.secondary
    c = frame.command_state
    print(
        f"  [{frame.tick_number:>3}] "
        f"flow={p.flow_rate:>6.1f}  "
        f"press={p.downstream_pressure:>5.3f} bar  "
        f"conc={p.chemical_concentration:>5.3f} mg/L  "
        f"power={s.pump_power_draw:>5.3f} kW  "
        f"cond={s.downstream_conductivity:>6.1f} µS/cm  "
        f"valve={'O' if c.valve_open else 'X'}  "
        f"anomaly={frame.active_anomaly or '—'}"
    )


plant = WaterTreatmentPlant()

print("=== Normal operation ===")
for _ in range(5):
    row(plant.tick())

print("\n=== Sensor spoof: FT-101 falsified, V-101 closed ===")
plant.inject_anomaly("sensor_spoof")
for _ in range(5):
    row(plant.tick())

print("\n=== Cleared — recovery ===")
plant.clear_anomaly()
for _ in range(4):
    row(plant.tick())

print("\n=== Slow drift attack on AT-101 (10 ticks) ===")
plant.inject_anomaly("slow_drift")
for _ in range(10):
    row(plant.tick())

print("\n=== Cleared — recovery ===")
plant.clear_anomaly()
for _ in range(4):
    row(plant.tick())

print("\n=== Pump failure: P-101 commanded on, mechanically dead ===")
plant.inject_anomaly("pump_failure")
for _ in range(5):
    row(plant.tick())

print("\n=== Cleared — recovery ===")
plant.clear_anomaly()
for _ in range(5):
    row(plant.tick())

print("\n=== Replay attack: readings frozen while dosing continues ===")
plant.inject_anomaly("replay_attack")
for _ in range(8):
    row(plant.tick())

print("\n=== Cleared ===")
plant.clear_anomaly()
for _ in range(3):
    row(plant.tick())

print("\n=== Recirculation mode ===")
plant.set_mode("recirculation")
for _ in range(5):
    row(plant.tick())
