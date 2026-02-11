from flask import Flask, request, jsonify, render_template
import requests
import os
import json

app = Flask(__name__)

BASE_ROOT = "https://api.ambeedata.com"


def load_env_file():
    """
    Minimal .env loader for local development (does nothing if .env is missing).
    """
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError as exc:
        print(f"Warning: could not read .env file: {exc}")


load_env_file()

# Read API key from environment to avoid hardcoding secrets.
# Support common env var names for convenience.
API_KEY = os.environ.get("AMBEE_API_KEY") or os.environ.get("AMBEEDATA_API_KEY")


def calculate_fire_index(fire):
    """
    Calculates a Fire Risk Index (0-100) based on fire intensity.
    """
    try:
        frp = fire.get("frp", 0)
        fwi = fire.get("fwi", 0)
        confidence = fire.get("confidence", "").lower()

        confidence_weight = {"high": 1.2, "nominal": 1.0, "low": 0.8}
        confidence_factor = confidence_weight.get(confidence, 1.0)

        index = min((frp * 2 + fwi * 10) * confidence_factor, 100)
        return round(index, 2)
    except Exception as exc:
        print(f"Error calculating fire index: {exc}")
        return 0


def fetch_ambee(endpoint, params):
    """
    Fetch data from the Ambee API with consistent error handling.
    """
    if not API_KEY:
        return {
            "data": [],
            "error": "Missing API key. Set AMBEE_API_KEY (or AMBEEDATA_API_KEY).",
            "status_code": 500,
        }

    headers = {
        "x-api-key": API_KEY,
        "Content-type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            f"{BASE_ROOT}{endpoint}",
            headers=headers,
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"API Request Error: {exc}")
        return {"data": [], "error": "Network error while contacting API.", "status_code": 502}

    if response.status_code != 200:
        print(f"API Error: {response.status_code} - {response.text}")
        message = "Failed to fetch data"
        try:
            err_payload = response.json()
            if isinstance(err_payload, dict):
                message = err_payload.get("message") or err_payload.get("error") or message
        except ValueError:
            pass
        return {"data": [], "error": message, "status_code": response.status_code}

    try:
        data = response.json()
    except ValueError:
        print("API Error: Invalid JSON response")
        return {"data": [], "error": "Invalid response from API.", "status_code": 502}

    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("data"), list):
        data["data"] = []
    return data


def enrich_latest_data(data):
    fires = data.get("data", [])
    for fire in fires:
        fire["fire_index"] = calculate_fire_index(fire)
    return data


def summarize_risk_entry(entry):
    if not isinstance(entry, dict):
        return str(entry)
    keys = [
        ("date", "date"),
        ("time", "time"),
        ("riskIndex", "risk"),
        ("risk", "risk"),
        ("fwi", "fwi"),
        ("danger", "danger"),
        ("temperature", "temp"),
        ("humidity", "humidity"),
        ("windSpeed", "wind"),
    ]
    parts = []
    for key, label in keys:
        if key in entry and entry[key] not in (None, ""):
            parts.append(f"{label}: {entry[key]}")
    if not parts:
        compact = json.dumps(entry, ensure_ascii=True)
        return compact[:140] + ("..." if len(compact) > 140 else "")
    return " | ".join(parts)


def compute_latest_stats(data_latest):
    fires = []
    if isinstance(data_latest, dict):
        fires = data_latest.get("data", [])
    count = len(fires) if isinstance(fires, list) else 0
    indices = []
    if isinstance(fires, list):
        for fire in fires:
            value = fire.get("fire_index")
            if isinstance(value, (int, float)):
                indices.append(value)
    avg_index = round(sum(indices) / len(indices), 2) if indices else 0
    return {"count": count, "avg_index": avg_index}


def get_fire_latest_by_place(place, fire_type=None):
    params = {"place": place}
    if fire_type:
        params["type"] = fire_type
    data = fetch_ambee("/fire/latest/by-place", params)
    return enrich_latest_data(data)


def get_fire_latest_by_coords(lat, lng, fire_type=None):
    params = {"lat": lat, "lng": lng}
    if fire_type:
        params["type"] = fire_type
    data = fetch_ambee("/fire/latest/by-lat-lng", params)
    return enrich_latest_data(data)


def get_fire_risk_by_place(place):
    return fetch_ambee("/fire/risk/by-place", {"place": place})


def get_fire_risk_by_coords(lat, lng):
    return fetch_ambee("/fire/risk/by-lat-lng", {"lat": lat, "lng": lng})


@app.route("/", methods=["GET", "POST"])
def home():
    data_latest = None
    data_risk = None
    place = request.form.get("place")
    lat = request.form.get("lat")
    lng = request.form.get("lng")
    mode = request.form.get("mode", "place")
    fire_type = request.form.get("type")

    if request.method == "POST":
        if mode == "coords":
            if not lat or not lng:
                data_latest = {"data": [], "error": "Latitude and longitude are required."}
                data_risk = {"data": [], "error": "Latitude and longitude are required."}
            else:
                try:
                    lat_val = float(lat)
                    lng_val = float(lng)
                except ValueError:
                    data_latest = {"data": [], "error": "Latitude/Longitude must be valid numbers."}
                    data_risk = {"data": [], "error": "Latitude/Longitude must be valid numbers."}
                else:
                    data_latest = get_fire_latest_by_coords(lat_val, lng_val, fire_type)
                    data_risk = get_fire_risk_by_coords(lat_val, lng_val)
        else:
            if not place:
                data_latest = {"data": [], "error": "Place is required."}
                data_risk = {"data": [], "error": "Place is required."}
            else:
                data_latest = get_fire_latest_by_place(place, fire_type)
                data_risk = get_fire_risk_by_place(place)

    risk_summaries = []
    if data_risk and isinstance(data_risk.get("data"), list):
        for entry in data_risk["data"][:6]:
            risk_summaries.append(summarize_risk_entry(entry))

    latest_stats = compute_latest_stats(data_latest)

    return render_template(
        "index.html",
        data_latest=data_latest,
        data_risk=data_risk,
        risk_summaries=risk_summaries,
        latest_stats=latest_stats,
        place=place,
        lat=lat,
        lng=lng,
        mode=mode,
        fire_type=fire_type or "",
    )


@app.route("/api/fire-data")
def fire_data():
    place = request.args.get("place")
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    fire_type = request.args.get("type")

    if place:
        return jsonify(get_fire_latest_by_place(place, fire_type))
    if lat and lng:
        try:
            return jsonify(get_fire_latest_by_coords(float(lat), float(lng), fire_type))
        except ValueError:
            return jsonify({"error": "Invalid latitude/longitude"})
    return jsonify({"error": "No place or coordinates provided"})


@app.route("/api/fire-risk")
def fire_risk():
    place = request.args.get("place")
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    if place:
        return jsonify(get_fire_risk_by_place(place))
    if lat and lng:
        try:
            return jsonify(get_fire_risk_by_coords(float(lat), float(lng)))
        except ValueError:
            return jsonify({"error": "Invalid latitude/longitude"})
    return jsonify({"error": "No place or coordinates provided"})


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
