import serial
from pymodbus.client import ModbusSerialClient as ModbusClient
import struct
import time
from datetime import datetime
from azure.storage.blob import BlobServiceClient

# === Azure Storage Connection ===
connect_str = "DefaultEndpointsProtocol=https;AccountName=batterylogsdata;AccountKey=70QmE7GVS+5fhCvBfnVlyOmyrBGuvow4Q+VPX3gMgdebFvbn9w2GKMmLjWhcE8KXMz+uIy9rtfkD+AStYu3aXw==;EndpointSuffix=core.windows.net"
container_name = "battery-logs"

blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_client = blob_service_client.get_container_client(container_name)

def log_data_to_azure(data):
    """Logs the data directly to Azure Blob Storage."""
    blob_name = datetime.now().strftime("%Y-%m-%d") + ".txt"  # Save data into today's file
    blob_client = container_client.get_blob_client(blob_name)

    try:
        existing_blob = blob_client.download_blob().readall().decode()
    except:
        existing_blob = ""

    new_blob = existing_blob + data + "\n"
    blob_client.upload_blob(new_blob, overwrite=True)

# === Modbus Connection Settings ===
gauge = ModbusClient(
    method="rtu",
    port="/dev/ttyUSB0",
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS
)

def read_parameters():
    """Read parameters from the Modbus device."""
    print("Connecting to Modbus device...")
    if not gauge.is_socket_open():
        if gauge.connect():
            print("Connected.")
        else:
            print("Failed to connect.")
            return None
    print("Reading registers...")
    try:
        def read_float_register(start_address, num_registers=2):
            result = gauge.read_input_registers(start_address, num_registers, slave=4)  # slave id is 4, which is what we set up in SDM 630
            if result.isError():
                print(f"Error reading address {start_address}: {result}")
                return None
            return struct.unpack('>f', struct.pack('>HH', *result.registers))[0]

        voltage_L3 = read_float_register(0x0004)
        current_L3 = read_float_register(0x000A)
        power_factor_L1 = read_float_register(0x001E)
        total_power_factor = read_float_register(0x003E)
        total_line_thd = read_float_register(0x00FA)

        return voltage_L3, current_L3, power_factor_L1, total_power_factor, total_line_thd
    except Exception as e:
        print(f"Exception while reading Modbus: {e}")
        return None

# === Main Loop ===
while True:
    parameters = read_parameters()
    if parameters is not None:
        voltage_L3, current_L3, power_factor_L1, total_power_factor, total_line_thd = parameters
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = (f"{timestamp}, Phase 2 Voltage: {voltage_L3:.2f}V, Phase 1 Current: {current_L3:.2f}A, "
                f"Phase 1 Power Factor: {power_factor_L1:.2f}, Total Power Factor: {total_power_factor:.2f}, "
                f"Total Line THD: {total_line_thd:.2f}%")
        log_data_to_azure(data)
        print(f"✅ Logged to Azure: {data}")
    else:
        print("❌ Failed to read Modbus data.")
    
    time.sleep(5)  # sleep 5 seconds between reads
