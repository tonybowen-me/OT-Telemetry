# Nalco-Type OT Cyber-Physical Validation — Demo Scope

## What We're Building

A demo of a three-layer cyber-physical security architecture for an industrial water treatment system. The system validates sensor telemetry against physical reality to detect spoofed, falsified, or manipulated data.

Core principle: **don't automatically trust your own sensor data.**

---

## Background

Based on the Nalco-Type OT Cyber-Physical Validation Architecture document (invariant-first, residual-second, causal-digital-twin-on-demand).

Three layers:
- **Layer 1 — Deterministic Invariants:** hard physics rules, binary pass/fail, no ML
- **Layer 2 — Residual Models:** graded trust scoring, detects slow drift
- **Layer 3 — Causal Digital Twin:** on-demand counterfactual reasoning, root cause analysis

Recommended positioning: *use invariants to reject the impossible, residuals to score the unlikely, and the causal digital twin to explain the ambiguous.*

---

## Demo Components

### 1. Simulated Sensor Data
- Fake water treatment plant emitting telemetry: flow, pressure, tank level, chemical concentration, pump states
- Runs normally by default
- Injectable anomaly scenarios: stuck sensor, spoofed reading, slow drift attack, pump failure

### 2. Layer 1 — Invariant Checker
- Hardcoded physics rules evaluated against each incoming reading
- Example rules:
  - If valve closed and bypass closed, downstream flow cannot exceed leakage threshold
  - If pump is off, downstream pressure cannot rise
  - Chemical dosing active while flow is zero is invalid unless recirculation mode is active
- Output: pass / fail / not applicable + explanation

### 3. Layer 2 — Residual Scorer
- Simple expected-vs-observed models per variable
- Rolling trust score per sensor
- Detects accumulating drift that wouldn't trip Layer 1
- Output: plausibility score + degraded telemetry indicator

### 4. Layer 3 — Counterfactual Engine
- Invoked only when Layers 1/2 flag ambiguity
- Generates candidate hypotheses (sensor spoof, actuator fault, pump failure, etc.)
- Tests each hypothesis against observed data
- Ranks explanations by causal consistency
- Output: most likely root cause + confidence + causal path

### 5. Dashboard
- Live sensor readings
- Per-sensor trust scores
- Active alerts with explanations
- Triggerable anomaly scenarios
- Root cause display when Layer 3 is invoked

---

## Tech Stack

- **Backend:** Python
- **Frontend:** React or plain HTML dashboard
- **Data:** Simulated — no real plant data required for demo

---

## Demo Scenarios (Triggerable)

| Scenario | Description | Expected Detection |
|----------|-------------|-------------------|
| Sensor spoof | Primary flow reading falsified while valve is closed | Layer 1 — flow continuity violation |
| Slow drift attack | Concentration reading gradually manipulated | Layer 2 — residual drift |
| Pump failure | Pump commanded on but power draw stays idle | Layer 1 — energy consistency violation |
| Replay attack | Old telemetry replayed during active dosing | Layer 2/3 — temporal inconsistency |
| Normal operation | No anomaly | All layers pass, trust scores high |

---

## Out of Scope for Demo

- Real P&ID or historian data
- SME-validated invariant library
- Production-grade causal graph (would require domain expertise + months of work)
- Full do-calculus causal engine

---

## Key Design Decisions to Make

- How many sensors to simulate (recommend starting with 5-8)
- Whether Layer 3 uses a simple rule-based counterfactual or a lightweight graph model
- Dashboard technology (React vs plain HTML)
- Whether to add an API layer between sim and dashboard
