import serial
from pymodbus.client import ModbusSerialClient as ModbusClient
import struct
import time
from datetime import datetime

# Configuration for Modbus connection
gauge = ModbusClient(
    method="rtu",
    port="/dev/ttyUSB0",
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS
)

def get_daily_log_filename():
    """Returns the filename based on current day of the week."""
    day_name = datetime.now().strftime("%A")  # e.g., "Monday"
    return f"/home/ben/Energy-Scout/logs/{day_name}.txt"

def log_data_to_file(data):
    """Logs the data to a text file named by day."""
    log_file = get_daily_log_filename()
    with open(log_file, "a") as file:
        file.write(data + "\n")

def read_parameters():
    """Read various parameters from the Modbus device."""
    print("Attempting to connect to the Modbus device...")
    if not gauge.is_socket_open():
        if gauge.connect():
            print("Connected successfully.")
        else:
            print("Failed to connect to the Modbus device.")
            return None
    print("Reading registers...")
    try:
        def read_float_register(start_address, num_registers=2):
            result = gauge.read_input_registers(start_address, num_registers)
            if result.isError():
                print(f"Error reading registers at address {start_address}: {result}")
                return None
            return struct.unpack('>f', struct.pack('>HH', *result.registers))[0]
        
        voltage_L3 = read_float_register(0x0004)
        current_L3 = read_float_register(0x000A)
        power_factor_L1 = read_float_register(0x001E)
        total_power_factor = read_float_register(0x003E)
        total_line_thd = read_float_register(0x00FA)
        
        return voltage_L3, current_L3, power_factor_L1, total_power_factor, total_line_thd
    except Exception as e:
        print(f"An exception occurred while reading parameters: {e}")
        return None

# Make sure the logs folder exists
import os
os.makedirs("/home/ben/Energy-Scout/logs", exist_ok=True)

# Main loop to read and log data periodically
while True:
    parameters = read_parameters()
    if parameters is not None:
        voltage_L3, current_L3, power_factor_L1, total_power_factor, total_line_thd = parameters
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = (f"{timestamp}, Phase 2 Voltage: {voltage_L3:.2f}V, Phase 1 Current: {current_L3:.2f}A, "
                f"Phase 1 Power Factor: {power_factor_L1:.2f}, Total Power Factor: {total_power_factor:.2f}, "
                f"Total Line THD: {total_line_thd:.2f}%")
        log_data_to_file(data)
        print(f"Logged data: {data}")
    else:
        print("Failed to read data from the Modbus device.")
    time.sleep(5)  # Adjust to 60 for real use
