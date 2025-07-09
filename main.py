import serial
from pymodbus.client import ModbusSerialClient as ModbusClient
import struct
import time
from datetime import datetime
import os
import requests
import urllib.request
import json
from urllib.parse import quote

# === FILE LOGGING SETUP ===
os.makedirs("/home/ben/Energy-Scout/logs", exist_ok=True)

def get_daily_log_filename():
    return f"/home/ben/Energy-Scout/logs/{datetime.now().strftime('%A')}.txt"

def log_data_to_file(data):
    with open(get_daily_log_filename(), "a") as f:
        f.write(data + "\n")

# === INFLUXDB SETUP ===
INFLUX_URL = "https://influxdb-production-d8c0.up.railway.app"
INFLUX_TOKEN = "scout-token-2024"
INFLUX_ORG = "EnergyScout"
INFLUX_BUCKET = "sensor_data"

def write_usb0_to_influx(voltage, current, pf, thd, power, city, temp_c, condition):
    line = f'energy_data,device=usb0 voltage={voltage},current={current},pf={pf},thd={thd},power={power},weather_temp_c={temp_c},weather_location="{city}",weather_condition="{condition}"'
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
            print("⚠️ Failed to write Main Device (usb0) to InfluxDB")
            print("📡 Payload:", line)
            print("📬 Status:", response.status_code)
            print("📝 Response:", response.text)
        else:
            print("✅ Main Device (usb0) Data written to InfluxDB")
    except Exception as e:
        print("❌ Exception while writing Main Device (usb0) to InfluxDB:", e)

def write_usb1_to_influx(voltage, current, power):
    line = f"energy_data,device=usb1 voltage={voltage},current={current},power={power}"
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
            print("⚠️ Failed to write USB1 Device to InfluxDB")
            print("📡 Payload:", line)
            print("📬 Status:", response.status_code)
            print("📝 Response:", response.text)
        else:
            print("✅ USB1 Device Data written to InfluxDB")
    except Exception as e:
        print("❌ Exception while writing USB1 Device to InfluxDB:", e)

# === WEATHER SETUP ===
WEATHER_API_KEY = "a5bfc0068cf949259eb41600250907"
WEATHER_CITY = "San Diego"
weather_data = None
weather_city = "Unknown"
weather_temp = 0.0
weather_condition = "Unknown"
last_weather_fetch = 0

def fetch_weather_data():
    global weather_data, weather_city, weather_temp, weather_condition, last_weather_fetch
    current_time = time.time()
    if current_time - last_weather_fetch > 900 or weather_data is None:
        try:
            url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={quote(WEATHER_CITY)}"
            with urllib.request.urlopen(url) as response:
                weather_data = json.loads(response.read().decode())
                last_weather_fetch = current_time
                print("🌤️ Weather data updated.")

                weather_temp = weather_data['current']['temp_c']
                weather_condition="{condition.replace(' ', '\\ ')}"
                weather_city = weather_data['location']['name']
        except Exception as e:
            print(f"⚠️ Failed to fetch weather data: {e}")

# === MODBUS SETUP ===
def get_modbus_client():
    for port in ["/dev/ttyUSB0", "/dev/ttyUSB1"]:
        client = ModbusClient(method="rtu", port=port, baudrate=9600, parity=serial.PARITY_NONE,
                              stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS)
        if client.connect():
            print(f"✅ Connected to Modbus device on {port}")
            return client
        else:
            print(f"❌ Could not connect to {port}")
    return None

gauge = get_modbus_client()
if gauge is None:
    print("❌ No Modbus devices found. Exiting.")
    exit(1)

def read_usb0_parameters():
    if not gauge.is_socket_open():
        if not gauge.connect():
            print("❌ Failed to reconnect to USB0 device.")
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
        power = abs(read_float_register(0x0034))

        return voltage, current, pf_l1, pf_total, thd, power

    except Exception as e:
        print(f"❌ Exception during USB0 device read: {e}")
        return None

def read_usb1_device():
    client_usb1 = ModbusClient(method="rtu", port="/dev/ttyUSB1", baudrate=9600,
                               parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                               bytesize=serial.EIGHTBITS, timeout=3)
    if not client_usb1.connect():
        print("❌ Failed to connect to USB1 Device.")
        return None
    try:
        result = client_usb1.read_input_registers(address=0, count=7, slave=1)
        if result.isError():
            print("⚠️ Error reading registers from USB1 Device")
            return None
        regs = result.registers
        return regs[0], regs[1], regs[2]
    except Exception as e:
        print(f"❌ Exception during USB1 Device read: {e}")
        return None
    finally:
        client_usb1.close()

# === MAIN LOOP ===
while True:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fetch_weather_data()

        parameters_usb0 = read_usb0_parameters()
        parameters_usb1 = read_usb1_device()

        if parameters_usb0 is not None:
            voltage, current, pf_l1, pf_total, thd, power = parameters_usb0
            log_line_usb0 = (f"{timestamp}, USB0 Device - Voltage: {voltage:.2f}V, Current: {current:.2f}A, "
                             f"PF L1: {pf_l1:.2f}, PF Total: {pf_total:.2f}, THD: {thd:.2f}%, Power: {power:.2f}W, "
                             f"Weather: {weather_city} | {weather_temp}°C | {weather_condition}")
            log_data_to_file(log_line_usb0)
            print("📄 Logged USB0 Device:", log_line_usb0)
            write_usb0_to_influx(voltage, current, pf_l1, thd, power, weather_city, weather_temp, weather_condition)
        else:
            log_data_to_file(f"{timestamp} ❌ Failed to read USB0 device")

        if parameters_usb1 is not None:
            v1, c1, p1 = parameters_usb1
            log_line_usb1 = f"{timestamp}, USB1 Device - Voltage: {v1}V, Current: {c1}A, Power: {p1}W"
            log_data_to_file(log_line_usb1)
            print("📄 Logged USB1 Device:", log_line_usb1)
            write_usb1_to_influx(v1, c1, p1)
        else:
            log_data_to_file(f"{timestamp} ❌ Failed to read USB1 device")

    except Exception as e:
        error_message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ❌ Exception in main loop: {e}"
        log_data_to_file(error_message)
        print(error_message)
        time.sleep(10)

    time.sleep(5)
