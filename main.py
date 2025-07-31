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
os.makedirs("/home/scout1/Energy-Scout/logs", exist_ok=True)

def get_daily_log_filename():
    return f"/home/scout1/Energy-Scout/logs/{datetime.now().strftime('%A')}.txt"

def log_data_to_file(data):
    with open(get_daily_log_filename(), "a") as f:
        f.write(data + "\n")

# === INFLUXDB SETUP ===
INFLUX_URL = "https://influxdb-production-d8c0.up.railway.app"
INFLUX_TOKEN = "scout-token-2024"
INFLUX_ORG = "EnergyScout"
INFLUX_BUCKET = "sensor_data"

def write_to_influx(device, **fields):
    line = f"energy_data,device={device} " + ",".join([f"{k}={v}" if not isinstance(v, str) else f'{k}="{v}"' for k, v in fields.items()])
    headers = {"Authorization": f"Token {INFLUX_TOKEN}", "Content-Type": "text/plain"}
    params = {"org": INFLUX_ORG, "bucket": INFLUX_BUCKET, "precision": "s"}
    try:
        response = requests.post(f"{INFLUX_URL}/api/v2/write", headers=headers, params=params, data=line)
        if response.status_code != 204:
            print(f"⚠️ Failed to write {device} to InfluxDB:", response.text)
        else:
            print(f"✅ {device} Data written to InfluxDB")
    except Exception as e:
        print(f"❌ Exception while writing {device} to InfluxDB:", e)

# === HARDCODED COORDINATES ===
lat = 35.63172
lon = -82.36431
city_name = "Asheville"

def write_location_to_influx(lat, lon, city):
    if lat is None or lon is None:
        return
    line = f'ip_location latitude={lat},longitude={lon},city="{city}"'
    headers = {"Authorization": f"Token {INFLUX_TOKEN}", "Content-Type": "text/plain"}
    params = {"org": INFLUX_ORG, "bucket": INFLUX_BUCKET, "precision": "s"}
    try:
        response = requests.post(f"{INFLUX_URL}/api/v2/write", headers=headers, params=params, data=line)
        if response.status_code != 204:
            print("⚠️ Failed to write location to InfluxDB:", response.text)
        else:
            print("✅ Hardcoded location written to InfluxDB")
    except Exception as e:
        print("❌ Error writing location to InfluxDB:", e)

# === WEATHER SETUP ===
WEATHER_API_KEY = "a5bfc0068cf949259eb41600250907"
WEATHER_CITY = f"{lat},{lon}"
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
                weather_condition = weather_data['current']['condition']['text'].replace("_", " ")
                weather_city = weather_data['location']['name']
        except Exception as e:
            print(f"⚠️ Failed to fetch weather data: {e}")

# === AC MODBUS CLIENT (USB0) ===
def get_modbus_client():
    client = ModbusClient(method="rtu", port="/dev/ttyUSB0", baudrate=9600, parity=serial.PARITY_NONE,
                          stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS)
    if client.connect():
        print("✅ Connected to AC Modbus device on /dev/ttyUSB0")
        return client
    else:
        print("❌ Could not connect to /dev/ttyUSB0")
        return None

gauge = get_modbus_client()
if gauge is None:
    print("❌ No AC Modbus devices found. Exiting.")
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
        thd = read_float_register(0x00F8)
        power = abs(read_float_register(0x0034))
        return voltage, current, pf_l1, thd, power

    except Exception as e:
        print(f"❌ Exception during USB0 device read: {e}")
        return None

# === NEW DC METER READERS (USB1 & USB2) ===
def read_dc_device(port):
    try:
        client = ModbusClient(method="rtu", port=port, baudrate=9600,
                              parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                              bytesize=serial.EIGHTBITS, timeout=2)
        if not client.connect():
            print(f"❌ Failed to connect to DC device on {port}")
            return None
        def read_param(start_addr, count, scale):
            rr = client.read_holding_registers(start_addr, count, slave=1)
            if rr.isError():
                return None
            raw = (rr.registers[0] << 16) + rr.registers[1]
            return raw / scale
        voltage = read_param(0x0100, 2, 10000)
        current = read_param(0x0102, 2, 10000)
        pf = read_param(0x010A, 2, 1000)
        client.close()
        return voltage, current, pf
    except Exception as e:
        print(f"❌ Exception during DC device read on {port}: {e}")
        return None

# === MAIN LOOP ===
while True:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fetch_weather_data()

        # AC Meter (USB0)
        parameters_usb0 = read_usb0_parameters()
        if parameters_usb0 is not None:
            voltage, current, pf, thd, power = parameters_usb0
            log_line_usb0 = (f"{timestamp}, USB0 AC - Voltage: {voltage:.2f}V, Current: {current:.2f}A, "
                             f"PF: {pf:.2f}, THD: {thd:.2f}%, Power: {power:.2f}W")
            log_data_to_file(log_line_usb0)
            print("📄 Logged AC Meter:", log_line_usb0)
            write_to_influx("usb0", voltage=voltage, current=current, pf=pf, thd=thd, power=power,
                            weather_temp_c=weather_temp, weather_location=weather_city, weather_condition=weather_condition)
        else:
            log_data_to_file(f"{timestamp} ❌ Failed to read AC meter")

        # DC Battery (USB1)
        battery_data = read_dc_device("/dev/ttyUSB1")
        if battery_data is not None:
            v_batt, c_batt, pf_batt = battery_data
            log_line_batt = f"{timestamp}, USB1 Battery - Voltage: {v_batt:.2f}V, Current: {c_batt:.2f}A, PF: {pf_batt:.3f}"
            log_data_to_file(log_line_batt)
            print("📄 Logged Battery DC:", log_line_batt)
            write_to_influx("usb1_battery", voltage=v_batt, current=c_batt, pf=pf_batt)
        else:
            log_data_to_file(f"{timestamp} ❌ Failed to read Battery DC")

        # DC Solar PV (USB2)
        solar_data = read_dc_device("/dev/ttyUSB2")
        if solar_data is not None:
            v_solar, c_solar, pf_solar = solar_data
            log_line_solar = f"{timestamp}, USB2 Solar - Voltage: {v_solar:.2f}V, Current: {c_solar:.2f}A, PF: {pf_solar:.3f}"
            log_data_to_file(log_line_solar)
            print("📄 Logged Solar DC:", log_line_solar)
            write_to_influx("usb2_solar", voltage=v_solar, current=c_solar, pf=pf_solar)
        else:
            log_data_to_file(f"{timestamp} ❌ Failed to read Solar DC")

        # Location
        location_log = f"{timestamp}, Location - Latitude: {lat:.6f}, Longitude: {lon:.6f}, City: {city_name}"
        log_data_to_file(location_log)
        print("📍 Logged Hardcoded Location:", location_log)
        write_location_to_influx(lat, lon, city_name)

    except Exception as e:
        error_message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ❌ Exception in main loop: {e}"
        log_data_to_file(error_message)
        print(error_message)
        time.sleep(10)

    time.sleep(5)
