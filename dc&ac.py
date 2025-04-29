import serial
from pymodbus.client import ModbusSerialClient as ModbusClient
import struct
import time
from datetime import datetime
import os
import requests

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

def write_to_influx(voltage, current, pf, thd, power, secondary_values=None):
    # Primary data
    line = f"energy_data voltage={voltage},current={current},pf={pf},thd={thd},power={power}"
    
    # If secondary device values exist, add them
    if secondary_values:
        for i, value in enumerate(secondary_values):
            line += f",secondary_reg_{i}={value}"

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

# === MODBUS DEVICE INITIALIZATION ===
def get_modbus_client(port, baudrate, parity):
    client = ModbusClient(
        method="rtu",
        port=port,
        baudrate=baudrate,
        parity=parity,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=3
    )
    if client.connect():
        print(f"✅ Connected to Modbus device on {port}")
        return client
    else:
        print(f"❌ Could not connect to {port}")
        return None

# Connect to Device 1 (Energy meter)
gauge = get_modbus_client("/dev/ttyUSB0", 9600, serial.PARITY_NONE)

# Connect to Device 2 (Secondary meter)
secondary_gauge = get_modbus_client("/dev/ttyUSB1", 2400, serial.PARITY_EVEN)

if gauge is None:
    print("❌ No primary Modbus device found. Exiting.")
    exit(1)
if secondary_gauge is None:
    print("⚠️ Warning: Secondary device not connected. Continuing without it.")

# === MODBUS READ FUNCTIONS ===
def read_parameters():
    if not gauge.is_socket_open():
        if not gauge.connect():
            print("❌ Failed to reconnect to Modbus device.")
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
        print(f"❌ Exception during Modbus read: {e}")
        return None

def read_secondary_device():
    if secondary_gauge is None:
        return None
    
    if not secondary_gauge.is_socket_open():
        if not secondary_gauge.connect():
            print("❌ Failed to reconnect to secondary Modbus device.")
            return None
    try:
        result = secondary_gauge.read_holding_registers(0, 5, unit=1)
        if result.isError():
            print("⚠️ Error reading secondary device registers.")
            return None
        return result.registers

    except Exception as e:
        print(f"❌ Exception during secondary device Modbus read: {e}")
        return None

# === MAIN LOOP ===
while True:
    parameters = read_parameters()
    secondary_values = read_secondary_device()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if parameters is not None:
        voltage, current, pf_l1, pf_total, thd, power = parameters

        # Prepare log line
        log_line = (
            f"{timestamp}, Voltage L3: {voltage:.2f}V, Current L3: {current:.2f}A, "
            f"PF L1: {pf_l1:.2f}, PF Total: {pf_total:.2f}, THD: {thd:.2f}%, "
            f"Power Total: {power:.2f}W"
        )

        # Add secondary readings if available
        if secondary_values:
            sec_line = ", Secondary Registers: " + ", ".join(map(str, secondary_values))
            log_line += sec_line

        # Log to file
        log_data_to_file(log_line)
        print("📄 Logged to file:", log_line)

        # Write to InfluxDB
        write_to_influx(voltage, current, pf_l1, thd, power, secondary_values=secondary_values)

    else:
        fail_msg = f"{timestamp} ❌ Failed to read Modbus data"
        log_data_to_file(fail_msg)
        print(fail_msg)

    time.sleep(5)
