from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

API_KEY = "c3ddfbc3bbccef5f1325f812b2478b592b64002af5b9cc96dbc2fc0837cd8823"
BASE_URL = "https://api.ambeedata.com/fire/latest/by-place"

def calculate_fire_index(fire):
    """
    Calculates a Fire Risk Index (0-100) based on fire intensity.
    """
    try:
        frp = fire.get("frp", 0)  
        fwi = fire.get("fwi", 0)  
        confidence = fire.get("confidence", "").lower()

        confidence_weight = {"high": 1.2, "nominal": 1.0, "low": 0.8}
        confidence_factor = confidence_weight.get(confidence, 1.0)  # Fixed lookup

        index = min((frp * 2 + fwi * 10) * confidence_factor, 100)

        return round(index, 2)
    except Exception as e:
        print(f"Error calculating fire index: {e}")
        return 0 


def get_fire_data(place):
    """
    Fetches wildfire data from the API and adds Fire Risk Index.
    """
    headers = {
        "x-api-key": API_KEY,
        "Content-type": "application/json"
    }
    params = {"place": place}
    
    response = requests.get(BASE_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()

        if "data" in data and isinstance(data["data"], list):
            for fire in data["data"]:
                fire["fire_index"] = calculate_fire_index(fire)
        
        return data  
    else:
        print(f"API Error: {response.status_code} - {response.text}")
        return {"error": "Failed to fetch data", "status_code": response.status_code}

@app.route("/", methods=["GET", "POST"])
def home():
    data = None
    place = request.form.get("place") 

    if place:
        data = get_fire_data(place) 

    return render_template("index.html", data=data, place=place)

@app.route("/api/fire-data")
def fire_data():
    place = request.args.get("place")
    if place:
        return jsonify(get_fire_data(place))
    return jsonify({"error": "No place provided"})

if __name__ == "__main__":
    app.run(debug=True)
