#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║      GODAVARI PUSHKARALU — AI SECURITY SYSTEM                              ║
# ║      SETUP & DEPENDENCY INSTALLER                                           ║
# ║      Run this ONCE before starting the application                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

set -e
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    GODAVARI PUSHKARALU AI SECURITY SYSTEM — SETUP v1.0      ║"
echo "║    Rajahmundry, Andhra Pradesh                               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}[1/6] Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    echo -e "${RED}ERROR: Python 3.9+ required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

echo -e "\n${BOLD}[2/6] Installing/verifying core Python packages...${NC}"

PACKAGES=(
    "numpy"
    "flask"
    "scipy"
    "scikit-learn"
    "opencv-python-headless"
    "Pillow"
    "mediapipe"
    "onnxruntime"
    "matplotlib"
)

FAILED_PACKAGES=()

for pkg in "${PACKAGES[@]}"; do
    PKG_NAME=$(echo $pkg | tr '[:upper:]' '[:lower:]' | sed 's/-/_/g' | sed 's/scikit_learn/sklearn/' | sed 's/pillow/PIL/' | sed 's/opencv_python_headless/cv2/')
    python3 -c "import $PKG_NAME" 2>/dev/null && echo -e "  ${GREEN}✓ $pkg${NC}" || {
        echo -e "  ${YELLOW}Installing $pkg...${NC}"
        pip install --break-system-packages --quiet "$pkg" 2>/dev/null && \
            echo -e "  ${GREEN}✓ $pkg installed${NC}" || {
            echo -e "  ${YELLOW}⚠ Could not install $pkg (may already be available)${NC}"
        }
    }
done

echo -e "\n${BOLD}[3/6] Verifying critical imports...${NC}"

python3 - <<'PYCHECK'
import sys
REQUIRED = {
    "flask": "Flask web framework",
    "numpy": "Numerical computing",
    "cv2": "Computer Vision (OpenCV)",
    "sklearn": "Machine Learning",
    "scipy": "Scientific computing",
    "PIL": "Image processing (Pillow)",
    "sqlite3": "Database (built-in)",
    "threading": "Concurrency (built-in)",
    "json": "JSON parsing (built-in)",
    "math": "Math functions (built-in)",
    "random": "Random numbers (built-in)",
    "time": "Time functions (built-in)",
    "datetime": "Date/time (built-in)",
    "collections": "Data structures (built-in)",
    "queue": "Thread-safe queues (built-in)",
    "hashlib": "Cryptographic hashing (built-in)",
    "base64": "Base64 encoding (built-in)",
}

failed = []
for module, desc in REQUIRED.items():
    try:
        __import__(module)
        print(f"  ✓ {module} — {desc}")
    except ImportError:
        print(f"  ✗ {module} — {desc} [MISSING]")
        failed.append(module)

OPTIONAL = {
    "onnxruntime": "ONNX model inference",
    "mediapipe": "Pose/crowd detection",
    "matplotlib": "Chart generation",
}
print("\nOptional (will use fallbacks if missing):")
for module, desc in OPTIONAL.items():
    try:
        __import__(module)
        print(f"  ✓ {module} — {desc}")
    except ImportError:
        print(f"  ○ {module} — {desc} [will use fallback]")

if failed:
    print(f"\nERROR: {len(failed)} required package(s) missing: {', '.join(failed)}")
    sys.exit(1)
print(f"\nAll required packages verified!")
PYCHECK

echo -e "\n${BOLD}[4/6] Creating directory structure...${NC}"
mkdir -p models data static/{css,js,img} templates logs exports
echo -e "${GREEN}✓ Directories ready${NC}"

echo -e "\n${BOLD}[5/6] Generating synthetic training data and SLM weights...${NC}"
python3 - <<'PYDATA'
import numpy as np, json, os, sqlite3, hashlib, time, random
from datetime import datetime, timedelta

print("  Generating crowd scenario training data...")

# Generate synthetic event scenarios for the SLM
GHAT_NAMES = [
    "Pushkar Ghat 1","Pushkar Ghat 2","Pushkar Ghat 3",
    "Kotipalli Ghat","Dhavaleswaram Ghat","Rajahmundry Main Ghat",
    "Boat Club Area","Lanka Ghat","Godavari Ardam Ghat","Havelock Bridge Ghat"
]

scenarios = []
for i in range(5000):
    density = random.uniform(0.5, 9.8)
    inflow = int(density * 12000 + random.gauss(0, 2000))
    outflow = int(inflow * random.uniform(0.6, 1.1))
    temp = random.uniform(25, 42)
    time_of_day = random.uniform(4, 22)
    rain = random.choice([0,0,0,0,1])
    is_peak = 1 if (6 <= time_of_day <= 10 or 16 <= time_of_day <= 20) else 0

    # Risk calculation (deterministic from features)
    risk = (
        density * 0.35 +
        (inflow - outflow) / 20000 * 2.0 +
        (1 - outflow / max(inflow, 1)) * 1.5 +
        (1 if density > 6 else 0) * 2.0 +
        rain * 0.5 +
        is_peak * 0.8 +
        random.gauss(0, 0.3)
    )
    risk = max(0, min(10, risk))

    # Alert level
    if density < 3:       level = 0  # GREEN
    elif density < 5:     level = 1  # YELLOW
    elif density < 7:     level = 2  # ORANGE
    else:                 level = 3  # RED

    # Suspicious activity labels
    suspicious = 1 if (
        (inflow > outflow * 1.4 and density > 5) or
        density > 8 or
        (rain and density > 4)
    ) else 0

    scenarios.append({
        "density": round(density, 2),
        "inflow": inflow,
        "outflow": outflow,
        "temp": round(temp, 1),
        "time_of_day": round(time_of_day, 1),
        "rain": rain,
        "is_peak": is_peak,
        "risk_score": round(risk, 3),
        "alert_level": level,
        "suspicious": suspicious,
        "ghat_idx": random.randint(0, 9)
    })

os.makedirs("data", exist_ok=True)
with open("data/training_scenarios.json", "w") as f:
    json.dump(scenarios, f)
print(f"  ✓ Generated {len(scenarios)} training scenarios")

# Generate historical crowd patterns (time-series per ghat)
print("  Generating historical crowd patterns...")
historical = {}
base_date = datetime(2025, 7, 1)
for ghat_idx, ghat in enumerate(GHAT_NAMES):
    series = []
    for day in range(12):  # 12-day event
        for hour in range(24):
            # Realistic crowd pattern: peaks at dawn & evening
            peak1 = np.exp(-((hour - 7) ** 2) / 8)   # dawn peak
            peak2 = np.exp(-((hour - 18) ** 2) / 10)  # evening peak
            base_density = (peak1 + peak2) * 6.5 * random.uniform(0.7, 1.3)
            # Ghat 2 and 7 are busier
            if ghat_idx in [2, 7]: base_density *= 1.4
            base_density = max(0.1, min(9.9, base_density + random.gauss(0, 0.5)))
            ts = (base_date + timedelta(days=day, hours=hour)).isoformat()
            series.append({"ts": ts, "density": round(base_density, 2), "day": day+1, "hour": hour})
    historical[ghat] = series

with open("data/historical_patterns.json", "w") as f:
    json.dump(historical, f)
print(f"  ✓ Generated {12*24*10} historical data points")

# Initialize SQLite DB
print("  Initializing database...")
conn = sqlite3.connect("data/godavari_security.db")
c = conn.cursor()

c.executescript("""
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ghat TEXT NOT NULL,
    alert_level INTEGER NOT NULL,
    density REAL,
    description TEXT,
    ai_response TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS camera_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT UNIQUE NOT NULL,
    ghat TEXT NOT NULL,
    status TEXT DEFAULT 'online',
    last_seen TEXT,
    density_reading REAL DEFAULT 0,
    person_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS crowd_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ghat TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    density REAL,
    inflow INTEGER,
    outflow INTEGER,
    risk_score REAL,
    alert_level INTEGER
);

CREATE TABLE IF NOT EXISTS slm_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    input_features TEXT,
    prediction TEXT,
    confidence REAL,
    response_text TEXT
);
""")

# Seed cameras
for g_idx, ghat in enumerate(GHAT_NAMES):
    for cam in range(random.randint(8, 16)):
        cam_id = f"CAM-{g_idx:02d}-{cam:03d}"
        c.execute("INSERT OR IGNORE INTO camera_feeds (camera_id, ghat, status, last_seen, density_reading, person_count) VALUES (?,?,?,?,?,?)",
                  (cam_id, ghat, "online", datetime.now().isoformat(), round(random.uniform(0.5,5.0),2), random.randint(50,800)))

# Seed some historical incidents
for _ in range(50):
    ghat = random.choice(GHAT_NAMES)
    level = random.randint(0, 3)
    ts = (datetime.now() - timedelta(hours=random.randint(0,72))).isoformat()
    c.execute("INSERT INTO incidents (timestamp, ghat, alert_level, density, description, ai_response, resolved) VALUES (?,?,?,?,?,?,?)",
              (ts, ghat, level, round(random.uniform(1,9),2),
               f"Crowd density alert at {ghat}", "Response team deployed", random.choice([0,1])))

conn.commit()
conn.close()
print("  ✓ Database initialized with seed data")
print("  All training data generated successfully!")
PYDATA

echo -e "\n${BOLD}[6/6] Training the SLM models...${NC}"
python3 - <<'PYTRAIN'
import numpy as np, json, os, pickle, time
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error

print("  Loading training data...")
with open("data/training_scenarios.json") as f:
    scenarios = json.load(f)

# Feature matrix
def extract_features(s):
    return [
        s["density"],
        s["inflow"],
        s["outflow"],
        s["inflow"] - s["outflow"],          # net flow
        s["inflow"] / max(s["outflow"], 1),  # flow ratio
        s["temp"],
        s["time_of_day"],
        np.sin(s["time_of_day"] * np.pi / 12),  # cyclic hour
        np.cos(s["time_of_day"] * np.pi / 12),
        s["rain"],
        s["is_peak"],
        s["ghat_idx"],
        s["density"] ** 2,                   # density squared (non-linear feature)
        1 if s["density"] > 5 else 0,        # high density flag
        1 if s["density"] > 7 else 0,        # critical flag
    ]

X = np.array([extract_features(s) for s in scenarios])
y_level = np.array([s["alert_level"] for s in scenarios])
y_risk  = np.array([s["risk_score"] for s in scenarios])
y_susp  = np.array([s["suspicious"] for s in scenarios])

os.makedirs("models", exist_ok=True)

# Scale features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_tr, X_te, y_ltr, y_lte = train_test_split(X_scaled, y_level, test_size=0.2, random_state=42)
_, _,    y_rtr, y_rte = train_test_split(X_scaled, y_risk,  test_size=0.2, random_state=42)
_, _,    y_str, y_ste = train_test_split(X_scaled, y_susp,  test_size=0.2, random_state=42)

print("  Training Alert Level Classifier (GBT)...")
clf_alert = GradientBoostingClassifier(n_estimators=150, max_depth=5, learning_rate=0.08, random_state=42)
clf_alert.fit(X_tr, y_ltr)
acc = accuracy_score(y_lte, clf_alert.predict(X_te))
print(f"  ✓ Alert Classifier — Accuracy: {acc*100:.1f}%")

print("  Training Risk Score Regressor (GBT)...")
reg_risk = GradientBoostingRegressor(n_estimators=150, max_depth=4, learning_rate=0.08, random_state=42)
reg_risk.fit(X_tr, y_rtr)
mae = mean_absolute_error(y_rte, reg_risk.predict(X_te))
print(f"  ✓ Risk Regressor    — MAE: {mae:.3f}")

print("  Training Suspicious Activity Detector (RF)...")
clf_susp = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
clf_susp.fit(X_tr, y_str)
acc2 = accuracy_score(y_ste, clf_susp.predict(X_te))
print(f"  ✓ Suspicious Detector — Accuracy: {acc2*100:.1f}%")

print("  Training Stampede Predictor (time-series)...")
# Simple next-step density predictor from historical patterns
with open("data/historical_patterns.json") as f:
    hist = json.load(f)

seq_X, seq_y = [], []
for ghat, series in hist.items():
    densities = [s["density"] for s in series]
    hours = [s["hour"] for s in series]
    for i in range(4, len(densities)-1):
        window = densities[i-4:i+1]
        feat = window + [hours[i], np.mean(window), np.std(window), max(window)-min(window)]
        seq_X.append(feat)
        seq_y.append(densities[i+1])

seq_X = np.array(seq_X)
seq_y = np.array(seq_y)
sc2 = StandardScaler()
seq_X_sc = sc2.fit_transform(seq_X)

reg_stamp = GradientBoostingRegressor(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42)
reg_stamp.fit(seq_X_sc, seq_y)
print(f"  ✓ Stampede Predictor  — trained on {len(seq_X)} sequences")

# Save all models
models_bundle = {
    "clf_alert":   clf_alert,
    "reg_risk":    reg_risk,
    "clf_susp":    clf_susp,
    "reg_stamp":   reg_stamp,
    "scaler":      scaler,
    "scaler_seq":  sc2,
    "feature_names": [
        "density","inflow","outflow","net_flow","flow_ratio",
        "temp","time_of_day","hour_sin","hour_cos","rain","is_peak",
        "ghat_idx","density_sq","high_density_flag","critical_flag"
    ],
    "label_names": ["GREEN","YELLOW","ORANGE","RED"],
    "version": "1.0.0"
}
with open("models/slm_bundle.pkl", "wb") as f:
    pickle.dump(models_bundle, f)

model_size = os.path.getsize("models/slm_bundle.pkl") / 1024
print(f"  ✓ All models saved → models/slm_bundle.pkl ({model_size:.0f} KB)")

# Save SLM response templates (the language generation component)
responses = {
    "GREEN": [
        "Crowd density at {ghat} is {density} persons/m² — within safe limits. Continue standard monitoring protocol.",
        "Zone {ghat} shows normal crowd flow. All parameters nominal. No action required.",
        "Current density {density} p/m² at {ghat} is acceptable. Routine surveillance active.",
    ],
    "YELLOW": [
        "⚠ ELEVATED ALERT: {ghat} density rising to {density} p/m². Recommend restricting new entries by 30%. Alert crowd management personnel.",
        "⚠ Crowd buildup detected at {ghat}: {density} p/m². Pre-position response team. Activate PA announcements directing pilgrims to alternate ghats.",
        "⚠ YELLOW STATUS at {ghat}. Net inflow positive by {net_flow:,}. Monitor closely — escalation possible within {eta:.0f} minutes if trend continues.",
    ],
    "ORANGE": [
        "🔴 HIGH RISK: {ghat} density {density} p/m² exceeds safe threshold. CLOSE ghat entry gates immediately. Deploy crowd dispersal team. Redirect to {alt_ghat}.",
        "🔴 ORANGE ALERT activated — {ghat}. Crowd model predicts {pred_density:.1f} p/m² in 15 minutes. Emergency response protocol initiated. All personnel report to Zone {zone_id}.",
        "🔴 URGENT: Bidirectional crowd flow detected at {ghat} ({density} p/m²). Stampede risk ELEVATED. Block entry, open all exit routes. Broadcast PA emergency message.",
    ],
    "RED": [
        "🚨 CRITICAL EMERGENCY — {ghat}: Density {density} p/m² — STAMPEDE RISK IMMINENT. FULL LOCKDOWN. Deploy Police + NDRF immediately. Activate mass emergency broadcast. Medical teams to Ghat {zone_id}.",
        "🚨 RED ALERT: {ghat} at {density} p/m² — LIFE THREATENING. Initiate emergency crowd dispersal. All available units to Zone {zone_id}. Sound alarm. Call District Collector now.",
        "🚨 MAXIMUM EMERGENCY — ALL UNITS RESPOND. {ghat} critical density {density} p/m². Evacuation initiated. Medical Emergency declared. Helicopter standby requested.",
    ],
    "SUSPICIOUS": [
        "⚠ AI Detection: Suspicious pattern at {ghat} — {reason}. Dispatching security officer to investigate. Camera {camera_id} recording.",
        "⚠ Anomaly detected by AI at {ghat}: {reason}. Risk score: {risk:.1f}/10. Operator review required.",
        "⚠ Behavioral anomaly at {ghat} — AI confidence {confidence:.0f}%. Likely: {reason}. Logging incident. Security alert dispatched.",
    ]
}
with open("models/response_templates.json", "w") as f:
    json.dump(responses, f, indent=2)
print("  ✓ Response templates saved")
print("\n  ✅ ALL MODELS TRAINED AND SAVED SUCCESSFULLY!")
PYTRAIN

echo -e "\n${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    SETUP COMPLETE!                           ║"
echo "║                                                              ║"
echo "║  To start the system, run:                                   ║"
echo "║  $ python3 app.py                                            ║"
echo "║                                                              ║"
echo "║  Then open browser at: http://localhost:5000                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
