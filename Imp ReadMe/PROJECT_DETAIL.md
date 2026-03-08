# Godavari Pushkaralu AI Security System — Project Documentation

## Overview
This project is an AI-powered security and crowd management system designed for the Godavari Pushkaralu event. It provides real-time monitoring, risk assessment, and actionable alerts for crowd safety at multiple ghats (riverbank areas). The system includes a live dashboard, AI-driven alerting, and a sophisticated crowd simulator for safe testing and demonstration.

---

## Main Components

### 1. **Flask Application (`app.py`)**
- **Purpose:** Serves the dashboard, REST API, and real-time data streams.
- **Features:**
  - Hosts the web dashboard for command center operators.
  - Provides real-time updates using Server-Sent Events (SSE).
  - Integrates with the AI engine and crowd simulator.

### 2. **Crowd Simulator (`crowd_simulator.py`)**
- **Purpose:** Generates realistic, real-time crowd data for all monitored ghats.
- **Features:**
  - Simulates crowd density, inflow/outflow, temperature, rain, camera status, and incidents.
  - Models time-of-day effects, random drift, and emergency scenarios.
  - Exposes data for use by the dashboard and AI engine.

### 3. **AI Engine (`slm_engine.py`)**
- **Purpose:** Core AI/ML logic for alerting, risk scoring, anomaly detection, and response generation.
- **Features:**
  - Loads trained ML models and response templates.
  - Predicts alert levels (GREEN, YELLOW, ORANGE, RED) based on real-time data.
  - Detects suspicious patterns and predicts stampede risk.
  - Generates actionable, context-aware alert messages.

### 4. **Data & Models**
- **`data/`**: Contains historical patterns, training scenarios, and the main SQLite database.
- **`models/`**: Stores the trained model bundle (`slm_bundle.pkl`) and response templates.

### 5. **Static & Templates**
- **`static/`**: CSS, JS, and image assets for the dashboard UI.
- **`templates/`**: Jinja2 HTML templates for rendering the dashboard and web pages.

---

## Alert Levels & Dashboard
- **GREEN:** Safe — Routine monitoring.
- **YELLOW:** Elevated — Restrict new entries, alert staff.
- **ORANGE:** High Risk — Close entry, deploy dispersal teams.
- **RED:** Critical — Full lockdown, emergency response.
- **SUSPICIOUS:** AI-detected anomalies (e.g., abnormal crowd behavior).
- Alerts are color-coded, real-time, and include recommended actions.

---

## Simulator Usage
- The simulator starts automatically with the app.
- Provides endpoints and functions for fetching live or sample data.
- Can simulate incidents for testing alert logic.

---

## Setup & Customization
- **Run `setup.sh`** to prepare models and data.
- Configure ghats, volatility, and incident rates in `crowd_simulator.py`.
- Adjust AI thresholds and templates in `slm_engine.py` and `models/response_templates.json`.

---

## Example Code Snippets
- **Start Simulator:**
  ```python
  simulator = CrowdSimulationEngine(tick_interval=2.5)
  ```
- **Get All Snapshots:**
  ```python
  snaps = simulator.get_all_snapshots()
  ```
- **Force Incident:**
  ```python
  simulator.force_incident("Pushkar Ghat 1")
  ```

---

## Summary
This project enables safe, AI-driven crowd management for large events. The simulator and dashboard allow for robust testing and real-time operational awareness, ensuring safety and rapid response during critical situations.
