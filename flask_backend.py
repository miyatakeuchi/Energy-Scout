from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Store data in memory (can be replaced with a database)
sensor_data = []

@app.route('/update-data', methods=['POST'])
def update_data():
    global sensor_data
    data = request.json
    data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sensor_data.append(data)  # Append new data
    return jsonify({"status": "success"}), 200

@app.route('/get-data', methods=['GET'])
def get_data():
    """Endpoint to fetch the latest 10 readings."""
    return jsonify(sensor_data[-10:])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)