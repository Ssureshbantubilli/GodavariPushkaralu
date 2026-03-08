# Crowd Simulator — Godavari Pushkaralu AI Security System

## Overview
The Crowd Simulator is a core component of the Godavari Pushkaralu AI Security System. It generates realistic, real-time crowd data for all monitored ghats (riverbank areas), simulating the kind of sensor and camera data that would be collected during the event.

## Purpose
- To provide a safe, controlled environment for testing and demonstrating the AI system.
- To enable development and validation of alert logic, dashboard features, and AI models without requiring real-world crowd data.

## How It Works
- The simulator runs as a background thread in the application.
- It manages a set of `GhatSimulator` instances, one for each ghat.
- Each `GhatSimulator` simulates:
  - Crowd density (persons per square meter)
  - Inflow and outflow rates
  - Temperature
  - Rain status
  - Camera status (number online/offline)
  - Person count
  - Incident (emergency) scenarios
- The simulation includes realistic features:
  - Time-of-day effects (peak hours, low hours)
  - Random drift and noise
  - Occasional incidents (density spikes)
  - Camera failures

## Data Provided
- The simulator exposes real-time snapshots for each ghat, including:
  - `ghat_name`: Name of the ghat
  - `density`: Current crowd density
  - `inflow` / `outflow`: People entering/leaving per hour
  - `person_count`: Estimated number of people present
  - `cameras_online` / `camera_count`: Camera status
  - `incident_active`: Whether an emergency is ongoing
  - `temp`: Temperature
  - `rain`: Rain status
  - `timestamp`: Time of the snapshot

## Integration
- The main Flask app imports and starts the simulator on launch.
- The dashboard and API endpoints use the simulator's data to display live metrics and trigger alerts.
- The `/sample-data` endpoint can be used to fetch a sample of the current simulated data for testing or demonstration.

## Customization
- The number of ghats, their base densities, and volatility can be configured in the `CrowdSimulationEngine` class.
- Incident frequency, camera failure rates, and other parameters can be adjusted for different scenarios.

## Example Usage
- The simulator is started automatically when the app runs:
  ```python
  simulator = CrowdSimulationEngine(tick_interval=2.5)
  ```
- To get a snapshot of all ghats:
  ```python
  snaps = simulator.get_all_snapshots()
  ```
- To force an incident at a specific ghat (for demo/testing):
  ```python
  simulator.force_incident("Pushkar Ghat 1")
  ```

## Summary
The Crowd Simulator is essential for developing, testing, and demonstrating the Godavari Pushkaralu AI Security System. It ensures the dashboard and alerting logic can be validated in a safe, repeatable way before deployment in the real world.
