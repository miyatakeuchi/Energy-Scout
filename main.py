import serial
from pymodbus.client import ModbusSerialClient as ModbusClient
import struct
import time
from datetime import datetime
import os
import paho.mqtt.client as mqtt
import json

# --- MQTT Setup ---
def on_connect(client, userdata, flags, rc):
    print("? Connected with result code " + str(rc))
    client.subscribe("sensor_data")

# Callback when a PUBLISH message is received from the server
def on_message(client, userdata, msg):
    print(f"?? Received on topic {msg.topic}: {msg.payload.decode()}")

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect("localhost", 1883)  # Change if broker is remote

# --- Modbus Configuration ---
gauge = ModbusClient(
    method="rtu",
    port="/dev/ttyUSB0",
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS
)

# --- Ensure log folder exists ---
os.makedirs("/home/ben/Energy-Scout/logs", exist_ok=True)

def get_daily_log_filename():
    """Get log file path based on current day."""
    day_name = datetime.now().strftime("%A")
    return f"/home/ben/Energy-Scout/logs/{day_name}.txt"

def log_data_to_file(data):
    """Append data to daily log file."""
    with open(get_daily_log_filename(), "a") as file:
        file.write(data + "\n")

def read_parameters():
    """Read float values from Modbus device."""
    if not gauge.is_socket_open():
        if not gauge.connect():
            print("? Failed to connect to Modbus device.")
            return None

    try:
        def read_float_register(start_address):
            result = gauge.read_input_registers(start_address, 2)
            if result.isError():
                print(f"? Error reading address {start_address}")
                return None
            return struct.unpack('>f', struct.pack('>HH', *result.registers))[0]

        voltage_L3 = read_float_register(0x0004)
        current_L3 = read_float_register(0x000A)
        power_factor_L1 = read_float_register(0x001E)
        total_power_factor = read_float_register(0x003E)
        total_line_thd = read_float_register(0x00FA)

        return voltage_L3, current_L3, power_factor_L1, total_power_factor, total_line_thd

    except Exception as e:
        print(f"?? Exception reading parameters: {e}")
        return None

# --- Main Loop ---
while True:
    parameters = read_parameters()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if parameters is not None:
        voltage_L3, current_L3, pf_L1, pf_total, thd = parameters

        # ?? Log to file
        data = (f"{timestamp}, Voltage L3: {voltage_L3:.2f}V, Current L3: {current_L3:.2f}A, "
                f"PF L1: {pf_L1:.2f}, PF Total: {pf_total:.2f}, THD: {thd:.2f}%")
        log_data_to_file(data)
        print("?? Logged to file:", data)

        # ?? Publish as JSON to topic 'sensor_data'
        payload = {
            "voltage": voltage_L3,
            "current": current_L3,
            "power_factor": pf_total,
            "thd": thd
        }
        mqtt_client.publish("sensor_data", json.dumps(payload))
        print("sent:",payload)
    else:
        fail_msg = f"{timestamp} Failed to read Modbus data"
        log_data_to_file(fail_msg)
        print(fail_msg)

    time.sleep(5)  # Wait 60 seconds before next reading
