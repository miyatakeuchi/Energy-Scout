from flask import Flask, request, jsonify
from datetime import datetime
import os

app = Flask(__name__)

# Ensure log folder
os.makedirs("logs", exist_ok=True)

@app.route("/")
def home():
    return "✅ Energy-Scout Flask Server is Running!"

@app.route("/log", methods=["POST"])
def log_data():
    data = request.json.get("data")
    if not data:
        return jsonify({"error": "No data provided"}), 400

    day = datetime.now().strftime("%A")
    with open(f"logs/{day}.txt", "a") as f:
        f.write(data + "\n")

    return jsonify({"message": "Data logged successfully"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
