# Troubleshooting Guide for RVR Controller

## Fixed Issues

### ImportError: cannot import name 'RvrLedGroups' or 'LedGroups'

**Issue:** The correct import path for LED groups was unclear

**Fix Applied:** Changed import from:
```python
from sphero_sdk.common.enums import LedGroups  # WRONG
```
to:
```python
from sphero_sdk import RvrLedGroups  # CORRECT
```

The `RvrLedGroups` enum is exported directly from the main `sphero_sdk` package. All LED control now uses `RvrLedGroups.all_lights.value` which is the proper SDK pattern.

### Missing 'dal' Parameter Error

**Issue:** `__init__() missing 1 required positional argument: 'dal'`

**Fix Applied:** The `SpheroRvrAsync` class requires a `dal` (Data Abstraction Layer) parameter. The RVR initialization is now deferred to the async `connect()` method:
```python
from sphero_sdk import SerialAsyncDal

# In async connect() method:
loop = asyncio.get_running_loop()  # Use get_running_loop() in async context
self.rvr = SpheroRvrAsync(dal=SerialAsyncDal(loop))
```

**Important:** Must use `get_running_loop()` (not `get_event_loop()`) when already in an async context to avoid "This event loop is already running" errors.

### Event Loop Already Running Error

**Issue:** `Fatal error: This event loop is already running` or `RuntimeError: This event loop is already running` during `SpheroRvrAsync` initialization

**Root Cause:** The Sphero SDK's `SpheroRvrAsync.__init__()` calls `_check_rvr_fw()` which uses `loop.run_until_complete()`. This fails when the event loop is already running (which it is in Python 3.7+ when using `asyncio.run()`).

**Fix Applied:**
1. Moved RVR initialization from `__init__()` to the async `connect()` method
2. Use `asyncio.get_running_loop()` instead of `asyncio.get_event_loop()`
3. Added `nest-asyncio` package to allow nested event loops (required for Sphero SDK compatibility)

The `nest_asyncio.apply()` is called at module import in `rvr_driver.py`, which patches the event loop to allow the SDK's synchronous calls within an async context.

**Manual Fix:** If you encounter this error, ensure `nest-asyncio` is installed:
```bash
pip3 install nest-asyncio
```

### Log File Permission Denied

**Issue:** Warning about not being able to create `/var/log/rvr-controller.log`

**Fix Applied:** Changed default config to use `null` (console only) instead of `/var/log/` which requires sudo permissions. Users can set a writable path like:
```yaml
logging:
  file: '~/rvr-controller.log'  # or null for console only
```

## Potential Issues and Solutions

### 1. Servo Control Method Not Found

**Symptom:** Error message about `set_all_pwms` not existing

**Solution:** The servo control implementation uses a try/catch fallback. If the method doesn't exist, it will log a warning but won't crash the program. Servo control will simply not work until you configure it properly.

**To properly set up servos on RVR:**

1. Check your RVR SDK version:
```python
import sphero_sdk
print(sphero_sdk.__version__)
```

2. Configure IO pins for servo output (add this to `rvr_driver.py` in the `connect()` method):
```python
# Configure pins for servo/PWM output
# Example: Configure ADI pins for servo control
await self.rvr.enable_motor_stall_notify(is_enabled=True)
# Check RVR SDK documentation for your specific model
```

3. Alternative servo control methods to try:
```python
# Method 1: Individual PWM
await self.rvr.set_io_pin_pwm_output(pin_id, duty_cycle)

# Method 2: All PWMs at once
await self.rvr.set_all_pwms([duty0, duty1, duty2, duty3])

# Method 3: Using raw API commands
await self.rvr.send_command_with_response(...)
```

### 2. Drive Commands Not Working

**Symptom:** RVR connects but doesn't move

**Possible causes:**
- Wrong UART baud rate (should be 115200)
- Wrong drive command flags
- RVR battery too low

**Solution:** Update the drive method in `rvr_driver.py`:

```python
async def drive(self, throttle: int, reverse: int, steering: int):
    if not self.connected:
        return

    try:
        speed = self.calculate_speed(throttle, reverse)
        heading = self.calculate_heading(steering)

        # Use raw_motors for direct control (alternative method)
        # await self.rvr.raw_motors(
        #     left_mode=1,  # Forward
        #     left_speed=abs(speed),
        #     right_mode=1,  # Forward
        #     right_speed=abs(speed)
        # )

        # Or use drive_with_heading (current method)
        await self.rvr.drive_with_heading(
            speed=abs(speed),
            heading=heading,
            flags=0  # Try flags=0 instead of 0x01/0x02
        )
```

### 3. Python 3.7 Compatibility Issues

**Symptom:** Syntax errors or import errors with Python 3.7

**Solution:** The code should work with Python 3.7+, but if you encounter issues:

1. Check Python version:
```bash
python3 --version
```

2. If using older Python, replace f-strings with `.format()`:
```python
# Old style (Python 3.5 compatible):
logger.info("Battery: {}%".format(battery['percentage']))

# Current style (Python 3.6+):
logger.info(f"Battery: {battery['percentage']}%")
```

### 4. Controller Not Detected

**Symptom:** "Controller with name pattern 'Victrix' not found"

**Solution:**

1. List all input devices:
```bash
ls -l /dev/input/
```

2. Find your controller:
```bash
sudo apt-get install evtest
sudo evtest
```

3. Update `config.yaml` with the correct device name:
```yaml
controller:
  device_name: 'YourControllerName'  # Use partial name from evtest
  # OR specify exact path:
  device_path: '/dev/input/event0'  # Use specific device
```

### 5. Permission Denied on /dev/serial0

**Symptom:** Cannot open UART port

**Solution:**

1. Check current permissions:
```bash
ls -l /dev/serial0
groups
```

2. Add user to dialout group (done by install.sh):
```bash
sudo usermod -a -G dialout $USER
```

3. Log out and back in, or use:
```bash
newgrp dialout
```

4. Verify UART is enabled:
```bash
sudo raspi-config
# Interface Options -> Serial Port
# - Login shell over serial: NO
# - Serial hardware enabled: YES
```

### 6. RVR Connection Timeout / Program Terminates

**Symptom:** "Failed to connect to RVR" or program terminates after "Connecting to RVR..."

**Possible causes:**
- Wrong UART wiring
- RVR not powered on
- RVR battery dead
- Wrong UART device
- Permission issues on /dev/serial0
- UART not enabled in raspi-config

**Solution:**

1. **Enable DEBUG logging** to see detailed error messages in `config.yaml`:
```yaml
logging:
  level: 'DEBUG'
```

2. **Check UART device exists and has permissions:**
```bash
ls -l /dev/serial0 /dev/ttyAMA0 /dev/ttyS0
# Should show: /dev/serial0 -> ttyAMA0
# Check you're in dialout group:
groups
```

3. **Test UART communication:**
```bash
sudo apt-get install minicom
minicom -b 115200 -o -D /dev/serial0
# You should see output when RVR is powered on
```

4. **Verify wiring:**
   - RVR TX → Pi RX (GPIO 15, Pin 10)
   - RVR RX → Pi TX (GPIO 14, Pin 8)
   - RVR GND → Pi GND (Pin 6)
   - Double-check you didn't swap TX/RX

5. **Verify RVR is powered on and charged:**
   - Press power button - should see LEDs
   - Try charging if battery is low

6. **Try different UART device** in `config.yaml`:
```yaml
rvr:
  uart_port: '/dev/ttyAMA0'  # Try this instead of /dev/serial0
  # Or try: '/dev/ttyS0'
```

7. **Check Sphero SDK is installed correctly:**
```bash
pip3 list | grep sphero
# Should show: sphero-sdk
```

8. **Run test script** to isolate the issue:
```python
#!/usr/bin/env python3
import asyncio
from sphero_sdk import SpheroRvrAsync, SerialAsyncDal

async def test():
    loop = asyncio.get_running_loop()
    rvr = SpheroRvrAsync(dal=SerialAsyncDal(loop))
    print("Created RVR instance")

    await rvr.wake()
    print("Wake command sent")
    await asyncio.sleep(2)

    battery = await rvr.get_battery_percentage()
    print(f"Battery: {battery}")

    await rvr.close()

asyncio.run(test())
```

### 7. High Latency / Slow Response

**Symptom:** Controller input is laggy

**Solution:**

1. Check CPU usage:
```bash
htop
```

2. Reduce logging in `config.yaml`:
```yaml
logging:
  level: 'WARNING'
  log_inputs: false
  log_commands: false
```

3. Disable unnecessary services:
```bash
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
```

4. Use Raspberry Pi OS Lite (no desktop)

5. Consider upgrading to Pi Zero 2 W for better performance

## Testing Individual Components

### Test Controller Only

Comment out RVR connection in `rvr_controller.py`:
```python
async def run(self):
    # ... controller connection code ...

    # Temporarily disable RVR for testing
    # if not await self.rvr.connect():
    #     logger.error("Failed to connect to RVR")
    #     return 1

    logger.info("Controller test mode - RVR disabled")
```

Run and check controller inputs in logs.

### Test RVR Only

Create a simple test script `test_rvr.py`:
```python
#!/usr/bin/env python3
import asyncio
from sphero_sdk import SpheroRvrAsync

async def main():
    rvr = SpheroRvrAsync()
    await rvr.wake()
    await asyncio.sleep(2)

    print("Getting battery...")
    battery = await rvr.get_battery_percentage()
    print(f"Battery: {battery['percentage']}%")

    print("Driving forward...")
    await rvr.drive_with_heading(speed=50, heading=0, flags=0)
    await asyncio.sleep(2)

    print("Stopping...")
    await rvr.drive_with_heading(speed=0, heading=0, flags=0)
    await asyncio.sleep(1)

    await rvr.close()
    print("Done!")

if __name__ == '__main__':
    asyncio.run(main())
```

Run:
```bash
python3 test_rvr.py
```

## Getting Help

If issues persist:

1. Check logs:
```bash
# If running manually:
python3 rvr_controller.py

# If running as service:
sudo journalctl -u rvr-controller.service -f
```

2. Enable debug logging in `config.yaml`:
```yaml
logging:
  level: 'DEBUG'
  log_inputs: true
  log_commands: true
```

3. Check Sphero SDK documentation:
   - https://github.com/sphero-inc/sphero-sdk-raspberrypi-python
   - Check examples in SDK repository

4. Report issues with:
   - Full error message
   - Python version (`python3 --version`)
   - Pi model (`cat /proc/device-tree/model`)
   - SDK version (`pip3 show sphero-sdk`)
   - Log output with debug enabled
