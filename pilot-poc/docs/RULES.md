# RULES — invariants, trust scores, and Sigma rules

All thresholds live in [`app/config.py`](../app/config.py). Nothing here is
learned; every value is declared and explainable.

## Layer 1 — deterministic invariants

Each returns `pass` / `fail` / `not_applicable`. A `fail` requires the condition
to persist for `SUSTAINED_VIOLATION_STEPS` (default 2) to avoid single-sample noise.

| rule | question | fails when |
|---|---|---|
| `INSUFFICIENT_DATA` | Is the required tag present? | tank-level missing ≥ `MIN_LEVEL_COVERAGE_STEPS` steps → drives **uncertain** |
| `TANK_MASS_BALANCE` | Does Δlevel match the inflow? | `|Δlevel − inflow·dt/area| > MASS_BALANCE_TOLERANCE_M` |
| `PUMP_ENERGY_CONSISTENCY` | Does pump status match flow? | status ON but flow ≈ 0 (or OFF but flowing) |
| `TANK_BOUNDS` | Is the level physically possible? | level outside `[TANK_MIN_LEVEL_M, TANK_MAX_LEVEL_M]` |

`TANK_MASS_BALANCE` is the invariant that catches the concealment MITM: the frozen
level reports Δ≈0 while the (uncompromised) inflow meter says the tank is draining.

### Mass balance derivation

The tank is a vertical cylinder of area `A = π·(D/2)²` (D = 31.3 m ⇒ A ≈ 769 m²).
Over one step `dt` the level must change by the net volume in divided by area:

```
Δlevel_expected = inflow[m³/s] · dt / A
```

`inflow` is the flow in the tank-feeding pipe `P15`, verified against `dV/dt` from
level (correlation ≈ 0.98 in the lab).

## Layer 2 — residual trust scoring

Rolling EMA (`L2_SMOOTHING`) of a per-sensor consistency signal in `[0,1]`.

| sensor | signal | verdict |
|---|---|---|
| `TANK.level` | mass-balance residual normalised by `5·tolerance` | `fail` < `L2_FAIL_THRESHOLD`, `warn` < `L2_WARN_THRESHOLD` |
| `PUMP.flow` | status/flow agreement | same thresholds |

Only a `fail` (hard trust collapse) escalates to Layer 3 — a transient `warn`
from an honest operational event does not.

## Layer 3 — counterfactual root cause

Engaged when L1 fails or L2 escalates. Deterministically scores hypotheses from
measurable signatures and returns the top-ranked cause with evidence:

| hypothesis | signature |
|---|---|
| `sensor_spoof_level` | mass balance fails while pump/inflow stay consistent |
| `pump_failure` | pump status/flow mismatch |
| `data_loss` | required tag missing |
| `drift` | L2 trust collapse with no hard invariant broken |

## Sigma — correlational baseline

Boolean threshold rules over **reported** telemetry only (no physical model):

| rule | expression | level |
|---|---|---|
| `tank_level_overflow` | `tank_level > 6.3` | high |
| `tank_level_low` | `tank_level < 1.0` | high |
| `low_pressure_J39` | `pressure_J39 < 15` | medium |
| `low_pressure_J156` | `pressure_J156 < 15` | medium |

These fire on the honest demand surge and stay silent on the concealment MITM
(whose reported values are all in-band) — the whole point of the demo.
