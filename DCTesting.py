from pymodbus.client import ModbusSerialClient
import time

client = ModbusSerialClient(
    port='COM6',
    baudrate=9600,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=3
)

if client.connect():
    print("✅ Connected!")

    while True:
        print("\n🔄 Reading registers...")

        # Read 5 registers at once (0 to 4)
        result = client.read_input_registers(address=0, count=7, slave=1)  # <<< read_input_registers

        if not result.isError():
            regs = result.registers
            voltage = regs[0]
            current = regs[1]
            power_low = regs[3]
            power_high = regs[4]

            # Calculate power
            power = (power_high << 16) + power_low

            print(f"🔋 Voltage = {voltage}")
            print(f"⚡ Current = {current}")
            print(f"💥 Power = {power}")
            print (result)
        else:
            print("⚠️ Error reading registers")

        time.sleep(5)

else:
    print("❌ Failed to connect.")
