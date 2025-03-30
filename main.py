import serial
from pymodbus.client import ModbusSerialClient as ModbusClient
import struct
import time
from datetime import datetime
import os
import paho.mqtt.client as mqtt
import json
import requests

# === MQTT SETUP (HiveMQ Cloud) ===
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set("EnergyScout1", "Atutu123")
mqtt_client.tls_set()
mqtt_client.connect("96d32576521941598cffab74430f6610.s1.eu.hivemq.cloud", 8883)
mqtt_client.loop_start()

# === MODBUS CONFIG ===
gauge = ModbusClient(
    method="rtu",
    port="/dev/ttyUSB0",
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS
)

# === FILE LOGGING SETUP ===
os.makedirs("/home/ben/Energy-Scout/logs", exist_ok=True)

def get_daily_log_filename():
    return f"/home/ben/Energy-Scout/logs/{datetime.now().strftime('%A')}.txt"

def log_data_to_file(data):
    with open(get_daily_log_filename(), "a") as f:
        f.write(data + "\n")

# === INFLUXDB SETUP (using working HTTP endpoint) ===
INFLUX_URL = "https://influxdb-production-d8c0.up.railway.app"
INFLUX_TOKEN = "scout-token-2024"
INFLUX_ORG = "EnergyScout"
INFLUX_BUCKET = "sensor_data"

def write_to_influx(voltage, current, pf, thd):
    line = f"energy_data voltage={voltage},current={current},pf={pf},thd={thd}"
    headers = {
        "Authorization": f"Token {INFLUX_TOKEN}",
        "Content-Type": "text/plain"
    }
    params = {
        "org": INFLUX_ORG,
        "bucket": INFLUX_BUCKET,
        "precision": "s"
    }
    try:
        response = requests.post(f"{INFLUX_URL}/api/v2/write", headers=headers, params=params, data=line)
        if response.status_code != 204:
            print("⚠️ Failed to write to InfluxDB")
            print("📡 Payload:", line)
            print("🧭 URL:", response.url)
            print("📬 Status:", response.status_code)
            print("📝 Response:", response.text)
        else:
            print("✅ Data written to InfluxDB")
    except Exception as e:
        print("❌ Exception while writing to InfluxDB:", e)

# === MODBUS READ FUNCTION ===
def read_parameters():
    if not gauge.is_socket_open():
        if not gauge.connect():
            print("❌ Failed to connect to Modbus device.")
            return None
    try:
        def read_float_register(start_addr):
            result = gauge.read_input_registers(start_addr, 2)
            if result.isError():
                print(f"⚠️ Error reading register {start_addr}")
                return None
            return struct.unpack('>f', struct.pack('>HH', *result.registers))[0]

        voltage = read_float_register(0x0004)
        current = read_float_register(0x000A)
        pf_l1 = read_float_register(0x001E)
        pf_total = read_float_register(0x003E)
        thd = read_float_register(0x00F8)

        return voltage, current, pf_l1, pf_total, thd

    except Exception as e:
        print(f"❌ Exception during Modbus read: {e}")
        return None

# === MAIN LOOP ===
while True:
    parameters = read_parameters()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if parameters is not None:
        voltage, current, pf_l1, pf_total, thd = parameters

        # Log to file
        log_line = f"{timestamp}, Voltage L3: {voltage:.2f}V, Current L3: {current:.2f}A, PF L1: {pf_l1:.2f}, PF Total: {pf_total:.2f}, THD: {thd:.2f}%"
        log_data_to_file(log_line)
        print("📄 Logged to file:", log_line)

        # Publish to MQTT
        mqtt_payload = {
            "voltage": voltage,
            "current": current,
            "power_factor": pf_total,
            "thd": thd
        }
        mqtt_client.publish("sensor_data", json.dumps(mqtt_payload))
        print("📤 Sent to MQTT:", mqtt_payload)

        # Write to InfluxDB
        write_to_influx(voltage, current, pf_total, thd)

    else:
        fail_msg = f"{timestamp} ❌ Failed to read Modbus data"
        log_data_to_file(fail_msg)
        print(fail_msg)

    time.sleep(5)
