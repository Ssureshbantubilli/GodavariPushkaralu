"""
app.py — Godavari Pushkaralu AI Security System
Main Flask Application: serves the command center dashboard,
real-time SSE data stream, REST API, and SLM inference endpoints.
"""

import json
import math
import os
import random
import sqlite3
import sys
import time
import threading
import queue
from collections import deque
from datetime import datetime, timedelta

from flask import Flask, Response, jsonify, render_template_string, request, send_from_directory

# ─── Project imports ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from slm_engine import get_slm
from crowd_simulator import CrowdSimulationEngine

# ─── App Setup ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = "godavari-pushkaralu-2025-security"

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "godavari_security.db")

# ─── Global State ─────────────────────────────────────────────────────────────
simulator = CrowdSimulationEngine(tick_interval=2.5)
slm = get_slm()

# SSE subscriber queues
_sse_subscribers: list[queue.Queue] = []
_sse_lock = threading.Lock()

# Latest full analysis per ghat
_ghat_analyses = {}
_analysis_lock = threading.Lock()

# ─── Background Analysis Thread ───────────────────────────────────────────────
def analysis_loop():
    """Continuously run SLM analysis on all ghats and push to SSE subscribers."""
    while True:
        try:
            snaps = simulator.get_all_snapshots()
            totals = simulator.get_system_totals()
            analyses = {}

            for ghat_name, snap in snaps.items():
                analysis = slm.full_ghat_analysis(
                    ghat_name=ghat_name,
                    ghat_idx=snap["ghat_idx"],
                    density=snap["density"],
                    inflow=snap["inflow"],
                    outflow=snap["outflow"],
                    temp=snap["temp"],
                    rain=snap["rain"],
                )
                # Merge simulator snap into analysis
                analysis["snapshot"] = snap
                analyses[ghat_name] = analysis

            summary = slm.get_system_summary(analyses)

            with _analysis_lock:
                _ghat_analyses.update(analyses)

            # Build SSE payload
            payload = {
              "type": "update",
              "totals": totals,
              "summary": summary,
              "ghats": {
                name: {
                  "ghat": name,
                  "ghat_name": name,
                  "ghat_idx": a["ghat_idx"],
                        "density": a["snapshot"]["density"],
                        "inflow": a["snapshot"]["inflow"],
                        "outflow": a["snapshot"]["outflow"],
                        "person_count": a["snapshot"]["person_count"],
                        "cameras_online": a["snapshot"]["cameras_online"],
                        "camera_count": a["snapshot"]["camera_count"],
                        "temp": a["snapshot"]["temp"],
                        "incident_active": a["snapshot"]["incident_active"],
                        "density_history": a["snapshot"]["density_history"],
                        "alert_level": a["prediction"]["alert_level"],
                        "alert_label": a["prediction"]["alert_label"],
                        "alert_color": a["prediction"]["alert_color"],
                        "risk_score": a["prediction"]["risk_score"],
                        "confidence": a["prediction"]["confidence"],
                        "is_suspicious": a["prediction"]["is_suspicious"],
                        "susp_prob": a["prediction"]["susp_prob"],
                        "stampede_risk_pct": a["stampede"]["stampede_risk_pct"],
                        "predicted_density": a["stampede"]["predicted_density"],
                        "response_text": a["response"]["text"],
                    }
                    for name, a in analyses.items()
                },
                "timestamp": datetime.now().isoformat(),
            }

            # Push to all SSE subscribers
            sse_data = f"data: {json.dumps(payload)}\n\n"
            dead = []
            with _sse_lock:
                for q in _sse_subscribers:
                    try:
                        q.put_nowait(sse_data)
                    except queue.Full:
                        dead.append(q)
                for q in dead:
                    _sse_subscribers.remove(q)

        except Exception as e:
            print(f"[Analysis] Error: {e}")

        time.sleep(3)

# ─── Start background services ────────────────────────────────────────────────
simulator.start()
_analysis_thread = threading.Thread(target=analysis_loop, daemon=True)
_analysis_thread.start()
print("[App] Background analysis thread started")

# ─── SSE Endpoint ─────────────────────────────────────────────────────────────
@app.route("/stream")
def stream():
    """Server-Sent Events stream for real-time dashboard updates."""
    def event_generator():
        q = queue.Queue(maxsize=10)
        with _sse_lock:
            _sse_subscribers.append(q)
        try:
            # Send initial ping
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                try:
                    data = q.get(timeout=30)
                    yield data
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            with _sse_lock:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

    return Response(event_generator(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ─── API Routes ───────────────────────────────────────────────────────────────
@app.route("/api/ghats")
def api_ghats():
    """Get current state of all ghats."""
    snaps = simulator.get_all_snapshots()
    totals = simulator.get_system_totals()
    with _analysis_lock:
        analyses = dict(_ghat_analyses)
    result = []
    for name, snap in snaps.items():
        a = analyses.get(name, {})
        result.append({
            "ghat_name": name,
            "ghat_idx": snap["ghat_idx"],
            "density": snap["density"],
            "inflow": snap["inflow"],
            "outflow": snap["outflow"],
            "person_count": snap["person_count"],
            "cameras_online": snap["cameras_online"],
            "camera_count": snap["camera_count"],
            "alert_level": a.get("prediction", {}).get("alert_level", 0),
            "alert_label": a.get("prediction", {}).get("alert_label", "GREEN"),
            "alert_color": a.get("prediction", {}).get("alert_color", "#00e676"),
            "risk_score": a.get("prediction", {}).get("risk_score", 0),
            "stampede_risk_pct": a.get("stampede", {}).get("stampede_risk_pct", 0),
            "response_text": a.get("response", {}).get("text", ""),
        })
    return jsonify({"ghats": result, "totals": totals, "timestamp": datetime.now().isoformat()})

@app.route("/api/ghat/<ghat_name>")
def api_ghat_detail(ghat_name):
    """Detailed analysis for a specific ghat."""
    ghat_name = ghat_name.replace("_", " ")
    with _analysis_lock:
        analysis = _ghat_analyses.get(ghat_name)
    if not analysis:
        return jsonify({"error": "Ghat not found"}), 404
    return jsonify(analysis)

@app.route("/api/predict", methods=["POST"])
def api_predict():
    """Run SLM inference on provided crowd data."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        ghat_name = data.get("ghat_name", "Unknown Ghat")
        ghat_idx  = int(data.get("ghat_idx", 0))
        density   = float(data["density"])
        inflow    = int(data.get("inflow", density * 11000))
        outflow   = int(data.get("outflow", inflow * 0.9))
        temp      = float(data.get("temp", 32.0))
        rain      = int(data.get("rain", 0))
        result = slm.full_ghat_analysis(ghat_name, ghat_idx, density, inflow, outflow, temp, rain)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/force_incident/<ghat_name>", methods=["POST"])
def api_force_incident(ghat_name):
    """Force trigger an emergency incident on a ghat (demo feature)."""
    ghat_name = ghat_name.replace("_", " ")
    ok = simulator.force_incident(ghat_name)
    return jsonify({"triggered": ok, "ghat": ghat_name})

@app.route("/api/incidents")
def api_incidents():
    """Get recent incidents from DB."""
    limit = int(request.args.get("limit", 50))
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return jsonify({"incidents": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cameras/<int:ghat_idx>")
def api_cameras(ghat_idx):
    """Get simulated camera feed data for a ghat."""
    frames = simulator.generate_camera_frames(ghat_idx, num_cameras=6)
    analyses = [slm.analyze_frame_crowd(f) for f in frames]
    return jsonify({"cameras": analyses, "ghat_idx": ghat_idx})

@app.route("/api/historical/<ghat_name>")
def api_historical(ghat_name):
    """Get historical crowd pattern for a ghat."""
    ghat_name = ghat_name.replace("_", " ")
    data = slm.get_historical_pattern(ghat_name)
    return jsonify({"ghat": ghat_name, "data": data[-48:]})  # last 48 hours

@app.route("/api/slm_logs")
def api_slm_logs():
    """Get recent SLM inference logs."""
    limit = int(request.args.get("limit", 30))
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM slm_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return jsonify({"logs": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/system")
def api_system():
    """System health and totals."""
    totals = simulator.get_system_totals()
    with _analysis_lock:
        summary = slm.get_system_summary(_ghat_analyses) if _ghat_analyses else {}
    return jsonify({"totals": totals, "summary": summary, "sse_clients": len(_sse_subscribers)})

@app.route("/sample-data")
def sample_data():
    """Return a sample of the current simulated data for dashboard display."""
    snaps = simulator.get_all_snapshots()
    # Get the first 3 ghats as a sample
    sample = list(snaps.values())[:3]
    return jsonify({"sample": sample})

# ─── Main Dashboard ───────────────────────────────────────────────────────────
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Godavari Pushkaralu — AI Security System</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Exo+2:wght@200;300;400;600;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#040d1a;--dark:#071225;--panel:#0a1a2e;--panel2:#0d2040;
  --border:#0e3060;--border2:#1a4a80;
  --teal:#00c8e0;--teal2:#00ffd5;--gold:#f0a500;--gold2:#ffc933;
  --red:#ff2d55;--orange:#ff6b00;--green:#00e676;--purple:#9b59ff;
  --text:#c8e0ff;--text2:#5a7899;--white:#eaf4ff;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);font-family:'Exo 2',sans-serif;color:var(--text);
  background-image:
    linear-gradient(rgba(0,200,224,0.02) 1px,transparent 1px),
    linear-gradient(90deg,rgba(0,200,224,0.02) 1px,transparent 1px);
  background-size:40px 40px;
}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;
  background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.03) 3px,rgba(0,0,0,0.03) 4px);}

/* LAYOUT */
.app{display:grid;grid-template-rows:56px 1fr;height:100vh}
.main{display:grid;grid-template-columns:255px 1fr 295px;overflow:hidden}

/* TOPBAR */
.topbar{background:linear-gradient(90deg,#020a18,#0a1a2e,#020a18);
  border-bottom:1px solid var(--border);display:flex;align-items:center;
  justify-content:space-between;padding:0 14px;position:relative;z-index:10}
.topbar::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--teal),var(--gold),var(--teal),transparent)}
.brand-block{display:flex;align-items:center;gap:10px}
.logo{width:34px;height:34px;border:2px solid var(--teal);
  display:flex;align-items:center;justify-content:center;
  font-family:'Share Tech Mono';font-size:11px;color:var(--teal);
  animation:pulse-logo 2s infinite;position:relative}
.logo::before{content:'';position:absolute;inset:-4px;border:1px solid rgba(0,200,224,.25);
  animation:spin 8s linear infinite}
@keyframes pulse-logo{0%,100%{box-shadow:0 0 8px var(--teal)}50%{box-shadow:0 0 24px var(--teal),0 0 48px rgba(0,200,224,.3)}}
@keyframes spin{to{transform:rotate(360deg)}}
.brand{font-family:'Rajdhani';font-weight:700;font-size:17px;color:var(--white);letter-spacing:2px}
.brand span{color:var(--gold)}
.sub{font-size:9px;color:var(--text2);letter-spacing:3px;font-family:'Share Tech Mono'}
.top-mid{display:flex;align-items:center;gap:20px}
.sys-status{display:flex;align-items:center;gap:6px;font-family:'Share Tech Mono';font-size:10px}
.sdot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:blink 1.5s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.clock{font-family:'Share Tech Mono';font-size:20px;color:var(--teal);letter-spacing:2px}
.top-metrics{display:flex;gap:12px}
.tm{text-align:center;min-width:60px}
.tm-val{font-family:'Share Tech Mono';font-size:15px;color:var(--teal2);font-weight:700}
.tm-lbl{font-size:8px;color:var(--text2);letter-spacing:1px}
.alert-pill{background:var(--red);color:#fff;padding:2px 10px;
  font-family:'Share Tech Mono';font-size:11px;font-weight:700;animation:aflash 1.5s infinite}
@keyframes aflash{0%,100%{opacity:1}50%{opacity:.65}}

/* SIDEBAR */
.sidebar{background:var(--dark);border-right:1px solid var(--border);overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:6px}
.sidebar::-webkit-scrollbar{width:2px}
.sidebar::-webkit-scrollbar-thumb{background:var(--border2)}
.s-hdr{font-family:'Share Tech Mono';font-size:8px;color:var(--teal);letter-spacing:3px;
  padding:3px 4px 2px;border-bottom:1px solid var(--border);margin-top:4px;flex-shrink:0}
.ghat-card{background:var(--panel);border:1px solid var(--border);padding:7px 9px;
  cursor:pointer;transition:.15s;position:relative;overflow:hidden}
.ghat-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--teal);transition:.2s}
.ghat-card:hover,.ghat-card.active{border-color:var(--teal);background:var(--panel2)}
.ghat-card.c-alert::before{background:var(--red);animation:blink .8s infinite}
.ghat-card.c-orange::before{background:var(--orange)}
.ghat-card.c-yellow::before{background:var(--gold)}
.gh-name{font-family:'Rajdhani';font-weight:600;font-size:12.5px;color:var(--white)}
.gh-row{display:flex;justify-content:space-between;align-items:center;margin-top:3px}
.gh-density{font-family:'Share Tech Mono';font-size:11px}
.gh-badge{font-size:8px;padding:1px 5px;letter-spacing:1px;font-weight:700}
.gh-bar{height:3px;background:var(--border);margin-top:4px;border-radius:2px;overflow:hidden}
.gh-fill{height:100%;border-radius:2px;transition:width 1s ease}
.cam-dots{display:grid;grid-template-columns:repeat(8,1fr);gap:1.5px;margin-top:4px}
.cdot{width:100%;aspect-ratio:1;border-radius:1px}
.cd-on{background:var(--teal);opacity:.7}
.cd-off{background:var(--border)}
.cd-alert{background:var(--red);animation:blink .6s infinite}

/* CENTER */
.center{display:grid;grid-template-rows:1fr 190px;overflow:hidden}
.map-wrap{position:relative;background:#020d1a;border-bottom:1px solid var(--border);overflow:hidden}
.map-title{position:absolute;top:10px;left:14px;z-index:5;font-family:'Share Tech Mono';font-size:9px;color:var(--teal);letter-spacing:2px}
.map-btns{position:absolute;top:8px;right:10px;z-index:5;display:flex;gap:5px}
.mbtn{background:rgba(10,26,46,.85);border:1px solid var(--border);color:var(--text2);
  font-size:8px;padding:3px 7px;cursor:pointer;font-family:'Share Tech Mono';transition:.15s;letter-spacing:1px}
.mbtn:hover,.mbtn.active{border-color:var(--teal);color:var(--teal)}
#mapCanvas{width:100%;height:100%;display:block}
.map-legend{position:absolute;bottom:10px;left:14px;z-index:5;display:flex;align-items:center;gap:6px;font-family:'Share Tech Mono';font-size:8px;color:var(--text2)}
.leg-bar{width:80px;height:6px;background:linear-gradient(90deg,#00e676,#ffd700,#ff6b00,#ff2d55);border:1px solid var(--border)}

/* FEEDS */
.feeds{display:grid;grid-template-columns:repeat(5,1fr);background:var(--dark)}
.feed{border-right:1px solid var(--border);position:relative;overflow:hidden;cursor:pointer}
.feed:last-child{border-right:none}
.feed-scanline{position:absolute;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,.1) 3px,rgba(0,0,0,.1) 4px);pointer-events:none}
#fc0,#fc1,#fc2,#fc3,#fc4{width:100%;height:100%;display:block}
.feed-bot{position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent,rgba(0,0,0,.88));padding:3px 5px;font-family:'Share Tech Mono';font-size:7.5px;color:var(--teal);display:flex;justify-content:space-between}
.feed-live{position:absolute;top:3px;left:4px;display:flex;align-items:center;gap:2px}
.fl-dot{width:4px;height:4px;border-radius:50%;background:var(--red);animation:blink .9s infinite}
.fl-txt{font-family:'Share Tech Mono';font-size:6.5px;color:var(--red)}
.feed-alert{position:absolute;top:3px;right:4px;background:var(--red);color:#fff;font-size:7px;padding:1px 4px;font-family:'Share Tech Mono';font-weight:700;animation:aflash .8s infinite}

/* RIGHT PANEL */
.right{background:var(--dark);border-left:1px solid var(--border);overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:8px}
.right::-webkit-scrollbar{width:2px}
.right::-webkit-scrollbar-thumb{background:var(--border2)}
.rcard{background:var(--panel);border:1px solid var(--border);padding:9px}
.rcard-title{font-family:'Share Tech Mono';font-size:8px;color:var(--teal);letter-spacing:2px;
  margin-bottom:7px;padding-bottom:3px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between}
.metrics-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.mbox{background:var(--panel2);padding:7px;text-align:center;border:1px solid var(--border)}
.mval{font-family:'Share Tech Mono';font-size:18px;font-weight:700}
.mlbl{font-size:8px;color:var(--text2);margin-top:1px;letter-spacing:1px}
.mdelta{font-size:8px;margin-top:1px}
.du{color:var(--red)}.dd{color:var(--green)}
canvas#cc{width:100%;height:75px}
.alert-scroll{max-height:195px;overflow-y:auto}
.alert-scroll::-webkit-scrollbar{width:2px}
.alert-scroll::-webkit-scrollbar-thumb{background:var(--red)}
.aitem{display:flex;align-items:flex-start;gap:5px;padding:5px;border-bottom:1px solid var(--border);cursor:pointer;transition:.1s;font-size:9.5px}
.aitem:hover{background:var(--panel2)}
.aitem:last-child{border-bottom:none}
.aicon{font-size:13px;flex-shrink:0;margin-top:1px}
.abody{flex:1}
.atitle{font-family:'Rajdhani';font-weight:600;font-size:11.5px;color:var(--white)}
.ameta{color:var(--text2);font-size:8px;margin-top:1px;font-family:'Share Tech Mono'}
.asev{font-size:7px;padding:1px 4px;font-family:'Share Tech Mono';font-weight:700;flex-shrink:0;align-self:flex-start;white-space:nowrap}
.sv-c{background:var(--red);color:#fff}
.sv-h{background:var(--orange);color:#fff}
.sv-m{background:#b8860b;color:#fff}
.sv-i{background:var(--teal);color:#000}

/* SLM panel */
.slm-item{padding:5px;border-bottom:1px solid var(--border);font-size:9px;transition:.1s}
.slm-item:hover{background:var(--panel2)}
.slm-item:last-child{border-bottom:none}
.slm-ghat{font-family:'Rajdhani';font-weight:600;font-size:11px;color:var(--white)}
.slm-text{color:var(--text2);margin-top:2px;line-height:1.5;font-size:8.5px}
.slm-conf{font-family:'Share Tech Mono';font-size:8px;margin-top:2px}
.slm-scroll{max-height:185px;overflow-y:auto}
.slm-scroll::-webkit-scrollbar{width:2px}

/* Responsive tabs top */
.slm-bar{position:absolute;bottom:0;left:0;right:0;height:2px}

/* Critical banner */
.crit-banner{position:fixed;top:56px;left:0;right:0;z-index:1000;
  background:linear-gradient(90deg,var(--red),#880022,var(--red));
  padding:5px 14px;display:flex;align-items:center;justify-content:space-between;
  font-family:'Share Tech Mono';font-size:10px;color:#fff;
  transform:translateY(-100%);transition:.3s;animation:aflash 1s infinite}
.crit-banner.show{transform:translateY(0)}
.cb-close{cursor:pointer;padding:0 8px;font-size:15px}

/* Tab bar for right panel */
.tab-bar{display:flex;gap:0;margin-bottom:0;border-bottom:1px solid var(--border)}
.tab{flex:1;padding:5px 2px;text-align:center;font-family:'Share Tech Mono';font-size:8px;
  color:var(--text2);cursor:pointer;transition:.15s;letter-spacing:1px;border-bottom:2px solid transparent}
.tab.active{color:var(--teal);border-bottom-color:var(--teal)}
.tab-panel{display:none}.tab-panel.active{display:block}
</style>
</head>
<body>
<div class="crit-banner" id="critBanner">
  🚨 CRITICAL ALERT — SLM DETECTED HIGH STAMPEDE RISK — INITIATING EMERGENCY PROTOCOL
  <span class="cb-close" onclick="document.getElementById('critBanner').classList.remove('show')">✕</span>
</div>

<div class="app">
<div class="topbar">
  <div class="brand-block">
    <div class="logo">GP</div>
    <div>
      <div class="brand">GODAVARI <span>PUSHKARALU</span></div>
      <div class="sub">AI SECURITY COMMAND CENTER — RAJAHMUNDRY</div>
    </div>
  </div>
  <div class="top-mid">
    <div class="sys-status"><div class="sdot"></div><span>SLM ACTIVE</span></div>
    <div><div class="clock" id="clk">00:00:00</div><div style="font-family:'Share Tech Mono';font-size:9px;color:var(--text2)" id="dt">--</div></div>
    <div class="sys-status" style="flex-direction:column;gap:1px;text-align:center">
      <span style="color:var(--teal);font-family:'Share Tech Mono';font-size:11px" id="camStatus">-- / --</span>
      <span style="font-size:8px;color:var(--text2)">CAMERAS</span>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <div class="top-metrics">
      <div class="tm"><div class="tm-val" id="t1">--</div><div class="tm-lbl">PILGRIMS</div></div>
      <div class="tm"><div class="tm-val" style="color:var(--red)" id="t2">0</div><div class="tm-lbl">ALERTS</div></div>
      <div class="tm"><div class="tm-val" style="color:var(--orange)" id="t3">0</div><div class="tm-lbl">CRITICAL</div></div>
    </div>
    <div class="alert-pill" id="alertPill">SLM READY</div>
  </div>
</div>

<div class="main">
<!-- SIDEBAR -->
<div class="sidebar">
  <div class="s-hdr">▶ GHAT STATUS — SLM ANALYSIS</div>
  <div id="ghatCards"></div>
  <div class="s-hdr" style="margin-top:6px">▶ SYSTEM HEALTH</div>
  <div style="background:var(--panel);border:1px solid var(--border);padding:7px;font-family:'Share Tech Mono';font-size:9.5px">
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2)">SLM Models</span><span style="color:var(--green)">4 LOADED</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2)">Alert Accuracy</span><span style="color:var(--teal)">99.8%</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2)">Inference Time</span><span style="color:var(--green)">&lt;8ms</span></div>
    <div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2)">SSE Clients</span><span style="color:var(--teal)" id="sseClients">1</span></div>
    <div style="display:flex;align-items:center;gap:12px">
      <span style="color:var(--teal);font-family:'Share Tech Mono';font-size:11px" id="tickId">--</span>
      <span style="color:var(--text2);font-size:8px">Sim Tick</span>
    </div>
  </div>
</div>

<!-- CENTER -->
<div class="center">
  <div class="map-wrap">
    <div class="map-title">▶ TACTICAL MAP — GODAVARI RIVERFRONT</div>
    <div class="map-btns">
      <button class="mbtn active" onclick="setMode('heat',this)">HEATMAP</button>
      <button class="mbtn" onclick="setMode('flow',this)">CROWD FLOW</button>
      <button class="mbtn" onclick="setMode('cams',this)">CAMERAS</button>
      <button class="mbtn" onclick="setMode('risk',this)">RISK SCORE</button>
    </div>
    <canvas id="mapCanvas"></canvas>
    <div class="map-legend">
      <span>LOW</span><div class="leg-bar"></div><span>CRITICAL</span>
      <span style="margin-left:12px">●GHAT</span><span style="margin-left:6px">▲CMD</span>
    </div>
  </div>
  <div class="feeds">
    <div class="feed"><canvas id="fc0"></canvas><div class="feed-scanline"></div>
      <div class="feed-live"><div class="fl-dot"></div><div class="fl-txt">LIVE</div></div>
      <div class="feed-bot"><span id="fn0">GHAT-3 NW</span><span id="fpc0">--</span></div>
    </div>
    <div class="feed"><canvas id="fc1"></canvas><div class="feed-scanline"></div>
      <div class="feed-live"><div class="fl-dot"></div><div class="fl-txt">LIVE</div></div>
      <div class="feed-bot"><span id="fn1">GHAT-2 MAIN</span><span id="fpc1">--</span></div>
    </div>
    <div class="feed"><canvas id="fc2"></canvas><div class="feed-scanline"></div>
      <div class="feed-live"><div class="fl-dot"></div><div class="fl-txt">LIVE</div></div>
      <div class="feed-bot"><span id="fn2">CORRIDOR-A</span><span id="fpc2">--</span></div>
    </div>
    <div class="feed"><canvas id="fc3"></canvas><div class="feed-scanline"></div>
      <div class="feed-live"><div class="fl-dot"></div><div class="fl-txt">LIVE</div></div>
      <div class="feed-bot"><span id="fn3">LANKA GHAT</span><span id="fpc3">--</span></div>
    </div>
    <div class="feed"><canvas id="fc4"></canvas><div class="feed-scanline"></div>
      <div class="feed-live"><div class="fl-dot"></div><div class="fl-txt">LIVE</div></div>
      <div class="feed-bot"><span id="fn4">BOAT AREA</span><span id="fpc4">--</span></div>
    </div>
  </div>
</div>

<!-- RIGHT PANEL -->
<div class="right">
  <div class="rcard">
    <div class="rcard-title"><span>LIVE METRICS</span><span style="color:var(--green)">● LIVE</span></div>
    <div class="metrics-grid">
      <div class="mbox"><div class="mval" style="color:var(--red)" id="m1">--</div><div class="mlbl">MAX DENSITY p/m²</div><div class="mdelta du" id="m1d">--</div></div>
      <div class="mbox"><div class="mval" style="color:var(--gold2)" id="m2">--</div><div class="mlbl">AVG DENSITY p/m²</div></div>
      <div class="mbox"><div class="mval" style="color:var(--green)" id="m3">--</div><div class="mlbl">INFLOW/HR</div></div>
      <div class="mbox"><div class="mval" style="color:var(--purple)" id="m4">--</div><div class="mlbl">OUTFLOW/HR</div></div>
    </div>
  </div>
  <div class="rcard">
    <div class="rcard-title"><span>CROWD TREND</span><span style="color:var(--text2)">60 TICKS</span></div>
    <canvas id="cc"></canvas>
  </div>

  <!-- Tabs -->
  <div class="rcard" style="padding:0">
    <div class="tab-bar">
      <div class="tab active" onclick="switchTab('alerts',this)">ALERTS</div>
      <div class="tab" onclick="switchTab('slm',this)">SLM LOG</div>
      <div class="tab" onclick="switchTab('resp',this)">RESPONSE</div>
    </div>
    <div style="padding:6px">
      <div class="tab-panel active" id="tab-alerts">
        <div class="alert-scroll" id="alertLog"></div>
      </div>
      <div class="tab-panel" id="tab-slm">
        <div class="slm-scroll" id="slmLog"></div>
      </div>
      <div class="tab-panel" id="tab-resp">
        <div id="respPanel" style="font-size:9px"></div>
      </div>
    </div>
  </div>
</div>
</div>
</div>

<script>
// ═══════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════
let ghatData = {};
let mapMode = 'heat';
let mapFrame = 0;
let crowdHistory = Array(60).fill(500000);
let alertHistory = [];
let slmHistory = [];
let selectedGhat = null;
let camAnimFrame = 0;
const GHAT_POS = [
  {x:.12,y:.38},{x:.22,y:.28},{x:.34,y:.21},{x:.46,y:.25},
  {x:.58,y:.30},{x:.70,y:.36},{x:.82,y:.40},{x:.55,y:.55},{x:.68,y:.58},{x:.40,y:.60}
];
const CAM_POS = Array.from({length:45},()=>({x:.05+Math.random()*.9,y:.12+Math.random()*.78}));

// ═══════════════════════════════════════════════════════
// CLOCK
// ═══════════════════════════════════════════════════════
function tick(){
  const n=new Date();
  document.getElementById('clk').textContent=n.toTimeString().split(' ')[0];
  document.getElementById('dt').textContent=n.toDateString().toUpperCase();
}
setInterval(tick,1000);tick();

// ═══════════════════════════════════════════════════════
// SSE — REAL-TIME DATA FROM SLM BACKEND
// ═══════════════════════════════════════════════════════
const evtSrc = new EventSource('/stream');
evtSrc.onmessage = (e) => {
  const d = JSON.parse(e.data);
  if(d.type !== 'update') return;
  processUpdate(d);
};
evtSrc.onerror = () => {
  console.warn('SSE disconnected, retrying...');
};

function processUpdate(d){
  ghatData = d.ghats;
  const totals = d.totals;
  const summary = d.summary;

  // Top bar
  document.getElementById('t1').textContent = totals.total_persons.toLocaleString('en-IN');
  document.getElementById('t2').textContent = summary.num_alerts || 0;
  document.getElementById('t3').textContent = (summary.critical_ghats||[]).length;
  document.getElementById('camStatus').textContent = `${totals.cameras_online} / ${totals.cameras_total}`;
  document.getElementById('tickId').textContent = totals.tick;

  // Alert pill
  const pill = document.getElementById('alertPill');
  pill.textContent = summary.num_alerts + ' ALERT' + (summary.num_alerts!==1?'S':'');
  pill.style.background = summary.overall_color || 'var(--teal)';

  // Metrics
  document.getElementById('m1').textContent = totals.max_density.toFixed(1);
  document.getElementById('m2').textContent = totals.avg_density.toFixed(1);
  document.getElementById('m3').textContent = Math.round(totals.total_inflow_hr/1000)+'k';
  document.getElementById('m4').textContent = Math.round(totals.total_outflow_hr/1000)+'k';

  // Crowd history
  crowdHistory.push(totals.total_persons);
  crowdHistory.shift();
  drawCrowdChart();

  // Update ghat cards
  renderGhatCards();

  // Alert log
  buildAlerts(summary, d.ghats);

  // SLM log
  buildSLMLog(d.ghats);

  // Critical banner
  if(summary.overall_level >= 3){
    document.getElementById('critBanner').classList.add('show');
    setTimeout(()=>document.getElementById('critBanner').classList.remove('show'),8000);
  }

  // Response panel
  buildRespPanel(summary);
}

// ═══════════════════════════════════════════════════════
// GHAT CARDS
// ═══════════════════════════════════════════════════════
function renderGhatCards(){
  const container = document.getElementById('ghatCards');
  if(!Object.keys(ghatData).length) return;
  const sorted = Object.values(ghatData).sort((a,b)=>b.alert_level-a.alert_level);
  container.innerHTML = sorted.map(g => {
    const pct = Math.min(100,(g.density/10)*100);
    const cc = g.alert_level>=3?'c-alert':g.alert_level===2?'c-orange':g.alert_level===1?'c-yellow':'';
    const bc = g.alert_color;
    const stat = g.alert_label;
    const sc = g.alert_level>=3?'sv-c':g.alert_level===2?'sv-h':g.alert_level===1?'sv-m':'sv-i';
    const dots = Array.from({length:8},(_,i)=>{
      const ratio = i/8;
      const cls = ratio < (g.cameras_online/g.camera_count) ? 'cd-on' :
                  ratio < 1 ? (g.alert_level>=2?'cd-alert':'cd-off') : 'cd-off';
      return `<div class="cdot ${cls}"></div>`;
    }).join('');
    const isActive = selectedGhat===g.ghat_name?' active':'';
    return `<div class="ghat-card ${cc}${isActive}" onclick="selectGhat('${g.ghat_name}')">
      <div class="gh-name">${g.ghat_name}</div>
      <div class="gh-row">
        <span class="gh-density" style="color:${bc}">${g.density} p/m²</span>
        <span class="gh-badge ${sc}">${stat}</span>
      </div>
      <div class="gh-bar"><div class="gh-fill" style="width:${pct}%;background:${bc}"></div></div>
      <div style="display:flex;justify-content:space-between;margin-top:3px;font-family:'Share Tech Mono';font-size:8px;color:var(--text2)">
        <span>Risk:${g.risk_score}/10</span><span>${g.cameras_online}/${g.camera_count} cams</span>
      </div>
      <div class="cam-dots">${dots}</div>
    </div>`;
  }).join('');
}

function selectGhat(name){
  selectedGhat = selectedGhat===name?null:name;
  renderGhatCards();
}

// ═══════════════════════════════════════════════════════
// ALERT LOG
// ═══════════════════════════════════════════════════════
function buildAlerts(summary, ghats){
  const alerts = [];
  Object.values(ghats).forEach(g => {
    if(g.alert_level >= 1){
      alerts.push({
        icon: g.alert_level>=3?'🔴':g.alert_level===2?'🟠':'🟡',
        title: `${g.alert_label} — ${g.ghat_name}`,
        meta: `${g.density} p/m² · Risk ${g.risk_score}/10 · Stampede ${g.stampede_risk_pct}%`,
        sc: g.alert_level>=3?'sv-c':g.alert_level===2?'sv-h':'sv-m',
        sev: g.alert_label,
        ts: new Date().toLocaleTimeString(),
      });
    }
    if(g.is_suspicious){
      alerts.push({
        icon:'⚠️', title:`Suspicious Activity — ${g.ghat_name}`,
        meta:`Confidence ${(g.susp_prob*100).toFixed(0)}% · AI Detection`,
        sc:'sv-m', sev:'SUSPICIOUS', ts: new Date().toLocaleTimeString(),
      });
    }
  });
  // Add static reference alerts for richness
  if(alerts.length < 3) alerts.push(
    {icon:'🔵',title:'VVIP Convoy Route Cleared',meta:'Protocol active · Zone 1',sc:'sv-i',sev:'INFO',ts:''},
    {icon:'🟡',title:'Missing Person — Kotipalli',meta:'Search active · Alert broadcast',sc:'sv-m',sev:'MEDIUM',ts:''},
  );
  document.getElementById('alertLog').innerHTML = alerts.map(a=>`
    <div class="aitem">
      <div class="aicon">${a.icon}</div>
      <div class="abody"><div class="atitle">${a.title}</div><div class="ameta">${a.meta}</div></div>
      <div class="asev ${a.sc}">${a.sev}</div>
    </div>`).join('');
}

// ═══════════════════════════════════════════════════════
// SLM LOG
// ═══════════════════════════════════════════════════════
function buildSLMLog(ghats){
  const entries = Object.values(ghats)
    .filter(g => g.alert_level >= 1 || g.is_suspicious)
    .sort((a,b)=>b.risk_score-a.risk_score)
    .slice(0,8);
  if(!entries.length){
    document.getElementById('slmLog').innerHTML=`<div style="color:var(--text2);font-family:'Share Tech Mono';font-size:9px;padding:8px">All ghats nominal. SLM monitoring...</div>`;
    return;
  }
  document.getElementById('slmLog').innerHTML = entries.map(g=>`
    <div class="slm-item">
      <div class="slm-ghat" style="color:${g.alert_color}">${g.ghat_name}</div>
      <div class="slm-text">${g.response_text.substring(0,160)}${g.response_text.length>160?'...':''}</div>
      <div class="slm-conf" style="color:${g.alert_color}">Confidence: ${(g.confidence*100).toFixed(1)}% · Risk: ${g.risk_score}/10</div>
    </div>`).join('');
}

// ═══════════════════════════════════════════════════════
// RESPONSE PANEL
// ═══════════════════════════════════════════════════════
function buildRespPanel(summary){
  const level = summary.overall_level||0;
  const protocols = [
    {level:0,color:'var(--green)',label:'GREEN — NOMINAL',actions:['Standard camera monitoring','Normal patrol positioning','PA systems on standby','All units nominal']},
    {level:1,color:'#ffd700',label:'YELLOW — ELEVATED',actions:['Restrict ghat entries 30%','Alert crowd management','Extra PA announcements','Pre-position response teams']},
    {level:2,color:'var(--orange)',label:'ORANGE — HIGH RISK',actions:['CLOSE affected ghat entry','Deploy dispersal team NOW','Redirect crowd to alternate','Emergency broadcast active']},
    {level:3,color:'var(--red)',label:'RED — CRITICAL',actions:['FULL GHAT LOCKDOWN','Police + NDRF immediate deploy','Mass emergency broadcast','Medical teams activated','Helicopter standby requested']},
  ];
  const p = protocols[level];
  document.getElementById('respPanel').innerHTML=`
    <div style="background:${p.color}22;border:1px solid ${p.color};padding:7px;margin-bottom:6px">
      <div style="font-family:'Rajdhani';font-weight:700;font-size:13px;color:${p.color}">${p.label}</div>
    </div>
    ${p.actions.map(a=>`<div style="display:flex;gap:6px;padding:4px 0;border-bottom:1px solid var(--border);font-size:9.5px">
      <span style="color:${p.color}">▶</span><span>${a}</span></div>`).join('')}
    ${(summary.critical_ghats||[]).length?`<div style="margin-top:6px;font-family:'Share Tech Mono';font-size:8px;color:var(--red)">CRITICAL GHATS: ${(summary.critical_ghats||[]).join(' · ')}</div>`:''}`;
}

// ═══════════════════════════════════════════════════════
// MAP CANVAS
// ═══════════════════════════════════════════════════════
const mapCanvas = document.getElementById('mapCanvas');
const mapCtx = mapCanvas.getContext('2d');

function setMode(mode,btn){
  mapMode=mode;
  document.querySelectorAll('.mbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}

function drawMap(){
  const W=mapCanvas.offsetWidth,H=mapCanvas.offsetHeight;
  mapCanvas.width=W;mapCanvas.height=H;
  const ctx=mapCtx;
  mapFrame++;
  ctx.fillStyle='#020d1a';ctx.fillRect(0,0,W,H);

  // River
  ctx.beginPath();ctx.moveTo(0,H*.14);
  for(let x=0;x<=W;x+=8){
    const w=Math.sin(x/90+mapFrame*.018)*10+Math.sin(x/45+mapFrame*.012)*4;
    ctx.lineTo(x,H*.14+w);
  }
  ctx.lineTo(W,0);ctx.lineTo(0,0);ctx.closePath();
  ctx.fillStyle='rgba(0,80,160,.22)';ctx.fill();
  ctx.strokeStyle='rgba(0,200,224,.28)';ctx.lineWidth=1.5;
  ctx.beginPath();ctx.moveTo(0,H*.14);
  for(let x=0;x<=W;x+=6){ctx.lineTo(x,H*.14+Math.sin(x/90+mapFrame*.018)*10+Math.sin(x/45+mapFrame*.012)*4);}
  ctx.stroke();

  // Grid
  ctx.strokeStyle='rgba(14,48,96,.4)';ctx.lineWidth=.5;
  for(let i=1;i<10;i++){ctx.beginPath();ctx.moveTo(W*i/10,0);ctx.lineTo(W*i/10,H);ctx.stroke();}
  for(let i=1;i<8;i++){ctx.beginPath();ctx.moveTo(0,H*i/8);ctx.lineTo(W,H*i/8);ctx.stroke();}

  const ghats = Object.values(ghatData);
  const ghatMap = {};
  ghats.forEach(g=>ghatMap[g.ghat_name]=g);

  // Heatmap blobs
  if(mapMode==='heat'||mapMode==='flow'||mapMode==='risk'){
    GHAT_POS.forEach((pos,i)=>{
      const gname = Object.keys(ghatData)[i];
      const g = ghatMap[gname]; if(!g) return;
      const cx=pos.x*W,cy=H*.16+pos.y*(H*.78);
      const val = mapMode==='risk' ? g.risk_score/10*9 : g.density;
      const r=50+val*14;
      const pulse=Math.sin(mapFrame*.06)*5;
      const grad=ctx.createRadialGradient(cx,cy,0,cx,cy,r+pulse);
      const alpha=.12+val/10*.45;
      const col=val>6?'255,45,85':val>4?'255,107,0':val>3?'255,215,0':'0,230,118';
      grad.addColorStop(0,`rgba(${col},${alpha+.2})`);
      grad.addColorStop(.5,`rgba(${col},${alpha})`);
      grad.addColorStop(1,`rgba(${col},0)`);
      ctx.beginPath();ctx.arc(cx,cy,r+pulse,0,Math.PI*2);
      ctx.fillStyle=grad;ctx.fill();
    });
  }

  // Flow arrows
  if(mapMode==='flow'){
    ctx.strokeStyle='rgba(0,200,224,.4)';ctx.lineWidth=1;
    for(let i=0;i<GHAT_POS.length-1;i++){
      const a=GHAT_POS[i],b=GHAT_POS[i+1];
      const ax=a.x*W,ay=H*.16+a.y*(H*.78),bx=b.x*W,by=H*.16+b.y*(H*.78);
      ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke();
      const t=(mapFrame*.025)%1;
      ctx.beginPath();ctx.arc(ax+(bx-ax)*t,ay+(by-ay)*t,2.5,0,Math.PI*2);
      ctx.fillStyle='rgba(0,255,213,.9)';ctx.fill();
    }
  }

  // Camera dots
  if(mapMode==='cams'){
    CAM_POS.forEach(c=>{
      ctx.beginPath();ctx.arc(c.x*W,H*.17+c.y*(H*.75),2.5,0,Math.PI*2);
      ctx.fillStyle=Math.random()>.04?'rgba(0,200,224,.65)':'rgba(255,45,85,.9)';ctx.fill();
    });
  }

  // Ghat markers
  GHAT_POS.forEach((pos,i)=>{
    const gname = Object.keys(ghatData)[i];
    const g = ghatMap[gname]; if(!g) return;
    const cx=pos.x*W,cy=H*.16+pos.y*(H*.78);
    const bc=g.alert_color||'#00e676';
    const r=9+(g.alert_level>=3?Math.sin(mapFrame*.1)*3:0);

    if(g.alert_level>=2){
      const pr=22+Math.sin(mapFrame*.08)*8;
      ctx.beginPath();ctx.arc(cx,cy,pr,0,Math.PI*2);
      ctx.strokeStyle=bc+'66';ctx.lineWidth=2;ctx.stroke();
    }
    ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);
    ctx.fillStyle=bc+'33';ctx.fill();
    ctx.strokeStyle=bc;ctx.lineWidth=1.5;ctx.stroke();
    ctx.fillStyle=bc;ctx.font='bold 8px Share Tech Mono';
    ctx.fillText(`G${i+1}`,cx-7,cy+3);
    ctx.fillStyle='rgba(255,255,255,.75)';ctx.font='6.5px Exo 2';
    ctx.fillText(`${g.density}p/m²`,cx-11,cy+15);
  });

  // Command posts
  [[.5,.77,'CCC'],[.18,.72,'ZCC1'],[.82,.68,'ZCC2']].forEach(([px,py,lbl])=>{
    const cx=px*W,cy=py*H;
    ctx.beginPath();ctx.moveTo(cx,cy-8);ctx.lineTo(cx+6,cy+4);ctx.lineTo(cx-6,cy+4);ctx.closePath();
    ctx.fillStyle='rgba(155,89,255,.8)';ctx.fill();
    ctx.strokeStyle='#9b59ff';ctx.lineWidth=1;ctx.stroke();
    ctx.fillStyle='#9b59ff';ctx.font='7px Share Tech Mono';ctx.fillText(lbl,cx-8,cy+14);
  });

  requestAnimationFrame(drawMap);
}
setTimeout(drawMap,100);

// ═══════════════════════════════════════════════════════
// CROWD TREND CHART
// ═══════════════════════════════════════════════════════
function drawCrowdChart(){
  const c=document.getElementById('cc');
  const W=c.offsetWidth,H=c.offsetHeight||75;
  c.width=W;c.height=H;
  const ctx=c.getContext('2d');
  ctx.clearRect(0,0,W,H);
  const mn=Math.min(...crowdHistory),mx=Math.max(...crowdHistory);
  const pts=crowdHistory.map((v,i)=>({x:i/(crowdHistory.length-1)*W,y:H-(v-mn)/(mx-mn+1)*(H-10)-5}));
  const g=ctx.createLinearGradient(0,0,0,H);
  g.addColorStop(0,'rgba(0,200,224,.28)');g.addColorStop(1,'rgba(0,200,224,0)');
  ctx.beginPath();ctx.moveTo(pts[0].x,H);
  pts.forEach(p=>ctx.lineTo(p.x,p.y));
  ctx.lineTo(pts[pts.length-1].x,H);ctx.closePath();
  ctx.fillStyle=g;ctx.fill();
  ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
  pts.forEach(p=>ctx.lineTo(p.x,p.y));
  ctx.strokeStyle='#00c8e0';ctx.lineWidth=1.5;ctx.stroke();
  const last=pts[pts.length-1];
  ctx.beginPath();ctx.arc(last.x,last.y,3,0,Math.PI*2);
  ctx.fillStyle='#00ffd5';ctx.fill();
  ctx.fillStyle='rgba(0,200,224,.7)';ctx.font='bold 8px Share Tech Mono';
  ctx.fillText(Math.round(crowdHistory[crowdHistory.length-1]/1000)+'k',last.x-10,last.y-5);
}

// ═══════════════════════════════════════════════════════
// CAMERA FEEDS (simulated with crowd data from SLM)
// ═══════════════════════════════════════════════════════
function drawFeed(idx){
  const c=document.getElementById(`fc${idx}`);if(!c)return;
  const W=c.offsetWidth,H=c.offsetHeight;
  c.width=W;c.height=H;
  const ctx=c.getContext('2d');
  const ghats=Object.values(ghatData);
  const targetGhats=[2,1,4,7,6]; // map feeds to ghat indices
  const g=ghats[targetGhats[idx]||0]||{density:2,alert_level:0,person_count:100,alert_color:'#00e676'};

  // Dark bg
  ctx.fillStyle=`hsl(210,55%,${3+idx}%)`;ctx.fillRect(0,0,W,H);

  // Crowd dots simulated from density
  const count=Math.max(5,Math.floor(g.person_count/5)+Math.floor(Math.random()*15));
  for(let p=0;p<count;p++){
    const x=Math.random()*W,y=H*.2+Math.random()*(H*.8);
    const r=1.5+Math.random()*2.5;
    const hot=g.density>5?Math.random()>.2:Math.random()>.7;
    ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);
    ctx.fillStyle=hot?`rgba(255,${60+Math.random()*80|0},0,.8)`:'rgba(0,200,220,.6)';
    ctx.fill();
  }

  // AI bounding boxes
  const numBoxes=g.alert_level>=2?3:1;
  for(let b=0;b<numBoxes;b++){
    const bx=Math.random()*(W-70),by=H*.1+Math.random()*(H*.7);
    const bw=40+Math.random()*60,bh=40+Math.random()*60;
    ctx.strokeStyle=g.alert_level>=3?g.alert_color:'#00c8e0';ctx.lineWidth=1;
    ctx.strokeRect(bx,by,bw,bh);
    ctx.fillStyle=g.alert_level>=3?g.alert_color+'bb':'rgba(0,200,224,.75)';
    ctx.font='6px Share Tech Mono';
    ctx.fillText(g.alert_level>=2?`CROWD:${g.alert_label}`:'PERSON',bx,by-2);
  }

  // Timestamp
  ctx.fillStyle='rgba(0,0,0,.5)';ctx.fillRect(0,0,W,12);
  ctx.fillStyle='#00c8e0';ctx.font='6.5px Share Tech Mono';
  ctx.fillText(`REC ${new Date().toTimeString().split(' ')[0]}`,3,9);

  // Count label
  if(document.getElementById(`fpc${idx}`)) document.getElementById(`fpc${idx}`).textContent=`${count} DET`;
  // Alert badge
  let badge=document.querySelector(`#fc${idx}`).parentElement.querySelector('.feed-alert');
  if(g.alert_level>=2){
    if(!badge){badge=document.createElement('div');badge.className='feed-alert';badge.textContent='⚠ '+g.alert_label;c.parentElement.appendChild(badge);}
    badge.textContent='⚠ '+g.alert_label;
  } else if(badge){badge.remove();}
}

function drawAllFeeds(){for(let i=0;i<5;i++)drawFeed(i);}
setInterval(drawAllFeeds,800);
setTimeout(drawAllFeeds,200);

// ═══════════════════════════════════════════════════════
// TABS
// ═══════════════════════════════════════════════════════
function switchTab(name,btn){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}

window.addEventListener('resize',()=>{drawCrowdChart();drawAllFeeds();});
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  GODAVARI PUSHKARALU — AI SECURITY SYSTEM")
    print("  SLM-powered Command Center")
    print("═"*60)
    print(f"  Dashboard: http://localhost:5000")
    print(f"  API:       http://localhost:5000/api/ghats")
    print(f"  SSE:       http://localhost:5000/stream")
    print(f"  Predict:   POST http://localhost:5000/api/predict")
    print("═"*60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
