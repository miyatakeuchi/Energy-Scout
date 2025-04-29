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

def write_to_influx(voltage, current, pf, thd, power):
    line = f"energy_data voltage={voltage},current={current},pf={pf},thd={thd},power={power}"
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
            print("⚠️ Failed to write Main Device to InfluxDB")
            print("📡 Payload:", line)
            print("🧭 URL:", response.url)
            print("📬 Status:", response.status_code)
            print("📝 Response:", response.text)
        else:
            print("✅ Main Device Data written to InfluxDB")
    except Exception as e:
        print("❌ Exception while writing Main Device to InfluxDB:", e)

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
            print("🧭 URL:", response.url)
            print("📬 Status:", response.status_code)
            print("📝 Response:", response.text)
        else:
            print("✅ USB1 Device Data written to InfluxDB")
    except Exception as e:
        print("❌ Exception while writing USB1 Device to InfluxDB:", e)

# === MODBUS DEVICE INITIALIZATION ===
def get_modbus_client():
    for port in ["/dev/ttyUSB0", "/dev/ttyUSB1"]:
        client = ModbusClient(
            method="rtu",
            port=port,
            baudrate=9600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS
        )
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

# === MODBUS READ FUNCTIONS ===
def read_parameters():
    if not gauge.is_socket_open():
        if not gauge.connect():
            print("❌ Failed to reconnect to Main Device.")
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
        print(f"❌ Exception during Main Device read: {e}")
        return None

def read_usb1_device():
    client_usb1 = ModbusClient(
        method="rtu",
        port="/dev/ttyUSB1",
        baudrate=9600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=3
    )

    if not client_usb1.connect():
        print("❌ Failed to connect to USB1 Device.")
        return None

    try:
        result = client_usb1.read_input_registers(address=0, count=7, slave=1)
        if result.isError():
            print("⚠️ Error reading registers from USB1 Device")
            return None

        regs = result.registers
        voltage = regs[0]
        current = regs[1]
        power_low = regs[3]
        power_high = regs[4]
        power = (power_high << 16) + power_low

        return voltage, current, power

    except Exception as e:
        print(f"❌ Exception during USB1 Device read: {e}")
        return None
    finally:
        client_usb1.close()

# === MAIN LOOP ===
while True:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Read Main Device
    parameters = read_parameters()

    # Read USB1 Device
    usb1_parameters = read_usb1_device()

    # ---- Main Device ----
    if parameters is not None:
        voltage, current, pf_l1, pf_total, thd, power = parameters

        log_line = (
            f"{timestamp}, Main Device - Voltage: {voltage:.2f}V, Current: {current:.2f}A, "
            f"PF L1: {pf_l1:.2f}, PF Total: {pf_total:.2f}, THD: {thd:.2f}%, "
            f"Power Total: {power:.2f}W"
        )
        log_data_to_file(log_line)
        print("📄 Logged Main Device:", log_line)

        write_to_influx(voltage, current, pf_l1, thd, power)

    else:
        fail_msg = f"{timestamp} ❌ Failed to read Modbus data (Main Device)"
        log_data_to_file(fail_msg)
        print(fail_msg)

    # ---- USB1 Device ----
    if usb1_parameters is not None:
        voltage_usb1, current_usb1, power_usb1 = usb1_parameters

        log_line_usb1 = (
            f"{timestamp}, USB1 Device - Voltage: {voltage_usb1}V, Current: {current_usb1}A, "
            f"Power: {power_usb1}W"
        )
        log_data_to_file(log_line_usb1)
        print("📄 Logged USB1 Device:", log_line_usb1)

        write_usb1_to_influx(voltage_usb1, current_usb1, power_usb1)

    else:
        fail_msg_usb1 = f"{timestamp} ❌ Failed to read Modbus data (USB1 Device)"
        log_data_to_file(fail_msg_usb1)
        print(fail_msg_usb1)

    time.sleep(5)
