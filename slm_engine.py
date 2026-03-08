"""
╔══════════════════════════════════════════════════════════════════╗
║  GODAVARI PUSHKARALU — SMALL LANGUAGE MODEL (SLM) ENGINE        ║
║  slm_engine.py — AI Core: Inference, Response Generation,       ║
║  Crowd Analytics, Anomaly Detection, Stampede Prediction         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import numpy as np
import pickle
import json
import math
import random
import os
import sqlite3
import time
from datetime import datetime, timedelta
from collections import deque
from sklearn.preprocessing import StandardScaler

# ─── Load Models ────────────────────────────────────────────────────────────────
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "slm_bundle.pkl")
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "models", "response_templates.json")
_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "godavari_security.db")

class GodavariSLM:
    """
    Small Language Model for Godavari Pushkaralu Security.
    Combines trained ML classifiers with template-based language generation
    to produce real-time situational awareness and actionable alerts.
    """

    ALERT_LEVELS = ["GREEN", "YELLOW", "ORANGE", "RED"]
    ALERT_COLORS = ["#00e676", "#ffd700", "#ff6b00", "#ff2d55"]
    ALERT_THRESHOLDS = [3.0, 5.0, 7.0, float("inf")]

    GHAT_NAMES = [
        "Pushkar Ghat 1","Pushkar Ghat 2","Pushkar Ghat 3",
        "Kotipalli Ghat","Dhavaleswaram Ghat","Rajahmundry Main Ghat",
        "Boat Club Area","Lanka Ghat","Godavari Ardam Ghat","Havelock Bridge Ghat"
    ]

    SUSPICIOUS_REASONS = [
        "Unattended object stationary for >2 minutes",
        "Abnormal crowd convergence pattern",
        "Person exhibiting erratic movement",
        "Unauthorized entry into restricted zone",
        "Crowd density spike without corresponding inflow increase",
        "Reverse flow against designated pedestrian direction",
        "Abandoned vehicle near ghat approach",
        "Overcrowding at single exit point",
    ]

    def __init__(self):
        self._load_models()
        self._load_templates()
        self._history = {g: deque(maxlen=24) for g in self.GHAT_NAMES}
        self._incident_queue = deque(maxlen=200)
        print(f"[SLM] Godavari SLM v1.0 initialized — {len(self.GHAT_NAMES)} ghats monitored")

    def _load_models(self):
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(f"Model bundle not found at {_MODEL_PATH}. Run setup.sh first.")
        with open(_MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        self.clf_alert  = bundle["clf_alert"]
        self.reg_risk   = bundle["reg_risk"]
        self.clf_susp   = bundle["clf_susp"]
        self.reg_stamp  = bundle["reg_stamp"]
        self.scaler     = bundle["scaler"]
        self.scaler_seq = bundle["scaler_seq"]
        self.label_names = bundle["label_names"]
        print(f"[SLM] Models loaded from {_MODEL_PATH}")

    def _load_templates(self):
        with open(_TEMPLATE_PATH) as f:
            self.templates = json.load(f)

    def _extract_features(self, density, inflow, outflow, temp, time_of_day, rain, is_peak, ghat_idx):
        net_flow = inflow - outflow
        flow_ratio = inflow / max(outflow, 1)
        return [
            density, inflow, outflow, net_flow, flow_ratio,
            temp, time_of_day,
            math.sin(time_of_day * math.pi / 12),
            math.cos(time_of_day * math.pi / 12),
            rain, is_peak, ghat_idx,
            density ** 2,
            1 if density > 5 else 0,
            1 if density > 7 else 0,
        ]

    def predict_alert(self, density, inflow, outflow, temp=32.0, time_of_day=None,
                       rain=0, ghat_idx=0):
        """Run full SLM inference on a ghat observation. Returns complete prediction."""
        if time_of_day is None:
            time_of_day = datetime.now().hour + datetime.now().minute / 60

        is_peak = 1 if (6 <= time_of_day <= 10 or 16 <= time_of_day <= 20) else 0

        features = self._extract_features(
            density, inflow, outflow, temp, time_of_day, rain, is_peak, ghat_idx
        )
        X = np.array([features])
        X_sc = self.scaler.transform(X)

        # Predictions
        alert_level = int(self.clf_alert.predict(X_sc)[0])
        alert_probs = self.clf_alert.predict_proba(X_sc)[0].tolist()
        risk_score  = float(self.reg_risk.predict(X_sc)[0])
        is_susp     = int(self.clf_susp.predict(X_sc)[0])
        susp_prob   = float(self.clf_susp.predict_proba(X_sc)[0][1])

        risk_score = max(0.0, min(10.0, risk_score))

        # Confidence = probability of predicted class
        confidence = alert_probs[alert_level]

        return {
            "alert_level":    alert_level,
            "alert_label":    self.ALERT_LEVELS[alert_level],
            "alert_color":    self.ALERT_COLORS[alert_level],
            "alert_probs":    [round(p, 3) for p in alert_probs],
            "risk_score":     round(risk_score, 2),
            "confidence":     round(confidence, 3),
            "is_suspicious":  bool(is_susp),
            "susp_prob":      round(susp_prob, 3),
            "features": {
                "density": density, "inflow": inflow, "outflow": outflow,
                "net_flow": inflow - outflow, "flow_ratio": round(inflow/max(outflow,1), 2),
                "is_peak": bool(is_peak), "rain": bool(rain),
            }
        }

    def predict_stampede(self, ghat_name, recent_densities, current_hour):
        """Predict crowd density for the next timestep using sequence model."""
        if len(recent_densities) < 5:
            # Pad with mean if insufficient history
            mean = np.mean(recent_densities) if recent_densities else 2.0
            recent_densities = [mean] * (5 - len(recent_densities)) + list(recent_densities)

        window = list(recent_densities[-5:])
        feat = window + [current_hour, np.mean(window), np.std(window), max(window) - min(window)]
        X = np.array([feat])
        X_sc = self.scaler_seq.transform(X)
        pred = float(self.reg_stamp.predict(X_sc)[0])
        pred = max(0.0, min(9.9, pred))

        # Stampede risk: if predicted density jumps significantly
        current = window[-1]
        delta = pred - current
        stampede_risk = max(0, min(100, (pred / 9.0) * 60 + max(0, delta) * 15))

        return {
            "predicted_density": round(pred, 2),
            "current_density":   round(current, 2),
            "delta":             round(delta, 3),
            "stampede_risk_pct": round(stampede_risk, 1),
            "eta_critical_min":  round(max(5, (7.0 - current) / max(delta, 0.01) * 60), 0) if delta > 0 and current < 7.0 else None,
        }

    def generate_response(self, ghat_name, prediction, stampede_pred=None, ghat_idx=0):
        """Generate natural language alert text using template engine + SLM logic."""
        level_label = prediction["alert_label"]
        density = prediction["features"]["density"]
        net_flow = prediction["features"]["net_flow"]
        risk = prediction["risk_score"]
        confidence = prediction["confidence"]

        # Pick alternate ghat for rerouting
        alt_ghats = [g for g in self.GHAT_NAMES if g != ghat_name]
        alt_ghat = random.choice(alt_ghats)
        zone_id = ghat_idx + 1

        # Get predicted density for ORANGE template
        pred_density = stampede_pred["predicted_density"] if stampede_pred else density + 0.3
        eta = stampede_pred["eta_critical_min"] if stampede_pred and stampede_pred.get("eta_critical_min") else 20

        template = random.choice(self.templates[level_label])
        try:
            response_text = template.format(
                ghat=ghat_name,
                density=density,
                net_flow=int(net_flow),
                alt_ghat=alt_ghat,
                zone_id=zone_id,
                pred_density=pred_density,
                eta=eta,
                risk=risk,
            )
        except (KeyError, ValueError):
            response_text = f"{level_label}: Crowd density {density} p/m² at {ghat_name}. Risk score: {risk:.1f}/10."

        # Add suspicious activity note
        susp_note = ""
        if prediction["is_suspicious"] and prediction["susp_prob"] > 0.5:
            reason = random.choice(self.SUSPICIOUS_REASONS)
            camera_id = f"CAM-{ghat_idx:02d}-{random.randint(0, 12):03d}"
            susp_tpl = random.choice(self.templates["SUSPICIOUS"])
            try:
                susp_note = " | " + susp_tpl.format(
                    ghat=ghat_name, reason=reason,
                    confidence=prediction["susp_prob"] * 100,
                    camera_id=camera_id, risk=risk
                )
            except:
                susp_note = f" | SUSPICIOUS ACTIVITY DETECTED at {ghat_name} (conf: {prediction['susp_prob']*100:.0f}%)"

        full_response = response_text + susp_note

        # Log to DB
        self._log_slm(prediction["features"], prediction, full_response, confidence)

        return {
            "text": full_response,
            "level": level_label,
            "color": prediction["alert_color"],
            "risk_score": risk,
            "confidence_pct": round(confidence * 100, 1),
            "suspicious": prediction["is_suspicious"],
            "ghat": ghat_name,
            "timestamp": datetime.now().isoformat(),
        }

    def analyze_frame_crowd(self, frame_data: dict) -> dict:
        """
        Analyze a simulated camera frame for crowd metrics.
        In production this would process actual video frames.
        frame_data: {camera_id, ghat_idx, width, height, person_count (simulated)}
        """
        person_count = frame_data.get("person_count", 0)
        area_m2 = frame_data.get("area_m2", 120.0)  # assumed area in m²
        density = person_count / max(area_m2, 1)

        # Detect anomalies in the frame
        anomalies = []
        if density > 6:
            anomalies.append({"type": "HIGH_DENSITY", "confidence": min(0.99, density/9), "bbox": [0.1,0.1,0.9,0.9]})
        if frame_data.get("has_unattended_object"):
            anomalies.append({"type": "UNATTENDED_OBJECT", "confidence": 0.87, "bbox": [0.4,0.3,0.6,0.5]})
        if frame_data.get("has_reverse_flow"):
            anomalies.append({"type": "REVERSE_FLOW", "confidence": 0.82, "bbox": [0.0,0.0,1.0,0.5]})

        return {
            "camera_id": frame_data.get("camera_id", "UNKNOWN"),
            "person_count": person_count,
            "density": round(density, 2),
            "anomalies": anomalies,
            "processed_at": datetime.now().isoformat(),
        }

    def full_ghat_analysis(self, ghat_name, ghat_idx, density, inflow, outflow,
                           temp=32.0, rain=0):
        """Complete pipeline: predict + stampede + generate response."""
        # Update history
        self._history[ghat_name].append(density)

        # Core prediction
        prediction = self.predict_alert(
            density, inflow, outflow, temp,
            ghat_idx=ghat_idx, rain=rain
        )

        # Stampede prediction from history
        hour = datetime.now().hour + datetime.now().minute / 60
        stampede_pred = self.predict_stampede(
            ghat_name, list(self._history[ghat_name]), hour
        )

        # Language generation
        response = self.generate_response(ghat_name, prediction, stampede_pred, ghat_idx)

        # Store incident if alert level >= YELLOW
        if prediction["alert_level"] >= 1:
            self._store_incident(ghat_name, prediction, response)

        return {
            "ghat": ghat_name,
            "ghat_idx": ghat_idx,
            "timestamp": datetime.now().isoformat(),
            "prediction": prediction,
            "stampede": stampede_pred,
            "response": response,
        }

    def _log_slm(self, features, prediction, response_text, confidence):
        try:
            conn = sqlite3.connect(_DB_PATH)
            conn.execute("""INSERT INTO slm_logs (timestamp, input_features, prediction, confidence, response_text)
                           VALUES (?,?,?,?,?)""",
                        (datetime.now().isoformat(), json.dumps(features),
                         prediction["alert_label"], confidence, response_text))
            conn.commit()
            conn.close()
        except: pass

    def _store_incident(self, ghat_name, prediction, response):
        try:
            conn = sqlite3.connect(_DB_PATH)
            conn.execute("""INSERT INTO incidents (timestamp, ghat, alert_level, density, description, ai_response)
                           VALUES (?,?,?,?,?,?)""",
                        (datetime.now().isoformat(), ghat_name, prediction["alert_level"],
                         prediction["features"]["density"], f"AI detected {prediction['alert_label']} alert",
                         response["text"]))
            conn.commit()
            conn.close()
        except: pass

    def get_historical_pattern(self, ghat_name):
        """Get historical crowd pattern for a ghat from DB."""
        try:
            with open(os.path.join(os.path.dirname(__file__), "data", "historical_patterns.json")) as f:
                hist = json.load(f)
            return hist.get(ghat_name, [])
        except:
            return []

    def get_system_summary(self, ghat_states):
        """Generate an executive summary of the whole system state."""
        levels = [s["prediction"]["alert_level"] for s in ghat_states.values()]
        max_density = max(s["prediction"]["features"]["density"] for s in ghat_states.values())
        critical = [g for g, s in ghat_states.items() if s["prediction"]["alert_level"] >= 2]
        total_risk = sum(s["prediction"]["risk_score"] for s in ghat_states.values()) / max(len(ghat_states), 1)

        overall = max(levels) if levels else 0
        return {
            "overall_level": overall,
            "overall_label": self.ALERT_LEVELS[overall],
            "overall_color": self.ALERT_COLORS[overall],
            "max_density": round(max_density, 2),
            "avg_risk": round(total_risk, 2),
            "critical_ghats": critical,
            "num_alerts": sum(1 for l in levels if l >= 1),
            "timestamp": datetime.now().isoformat(),
        }


# ─── Singleton instance ──────────────────────────────────────────────────────────
_slm_instance = None

def get_slm():
    global _slm_instance
    if _slm_instance is None:
        _slm_instance = GodavariSLM()
    return _slm_instance
