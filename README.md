# Sphero RVR Controller

Control your Sphero RVR robot with a Victrix BFG Pro game controller using a Raspberry Pi Zero W. Designed for headless operation with full systemd integration for auto-start on boot.

## Features

- **Proportional Control**: Right trigger for forward throttle, left trigger for reverse (0-255 speed range)
- **Analog Steering**: Left stick for precise directional control
- **Servo Control**: Control up to 4 servo channels via controller buttons
- **Safety Features**: Auto-stop on input timeout, emergency stop on connection loss
- **Headless Operation**: Runs without display, perfect for embedded robotics
- **Auto-start**: Systemd service for automatic startup on boot
- **Optimized for Pi Zero W**: Efficient asyncio architecture for limited hardware

## Hardware Requirements

- Raspberry Pi Zero W (recommended) or Pi Zero 2 W
- Sphero RVR robot
- Victrix BFG Pro controller (or compatible Xbox-style controller)
- 3 female-to-female jumper wires for UART connection
- microSD card (16GB+, Class 10 recommended)

## Hardware Setup

### UART Connection (RVR to Pi Zero W)

Connect the RVR's 4-pin UART port to the Pi Zero W GPIO pins:

| RVR UART Pin | Wire Color | Pi Zero W Pin | GPIO | Function |
|--------------|------------|---------------|------|----------|
| TX (pin 1)   | Red        | Pin 10        | GPIO 15 (RXD) | Receive |
| RX (pin 2)   | Yellow     | Pin 8         | GPIO 14 (TXD) | Transmit |
| GND (pin 3)  | Black      | Pin 6         | GND | Ground |
| 5V (pin 4)   | *Optional* | Pin 2         | 5V | Power (can power Pi) |

**Important Notes:**
- Both RVR and Pi use 3.3V logic levels - safe to connect directly
- RVR can supply 2.1A @ 5V, sufficient to power Pi Zero W
- Verify pin numbers on your specific RVR model

### Controller Connection

1. Connect Victrix BFG Pro controller to Pi Zero W via USB
2. Controller will auto-detect on boot
3. LED indicators on controller confirm connection

## Software Installation

### Quick Install

1. Clone or copy this repository to your Pi:
```bash
cd ~
git clone <repository-url> rvr
cd rvr
```

2. Run the installation script:
```bash
chmod +x install.sh
./install.sh
```

3. Reboot for UART changes to take effect:
```bash
sudo reboot
```

### Manual Installation

If you prefer manual setup:

1. **Enable UART in `/boot/config.txt`:**
```bash
echo "enable_uart=1" | sudo tee -a /boot/config.txt
```

2. **Disable console on serial in `/boot/cmdline.txt`:**
Remove `console=serial0,115200` from the line

3. **Install dependencies:**
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-dev
pip3 install -r requirements.txt --user
```

4. **Add user to groups:**
```bash
sudo usermod -a -G input,dialout $USER
```

5. **Reboot:**
```bash
sudo reboot
```

## Configuration

Edit `config.yaml` to customize behavior:

```yaml
controller:
  device_path: 'auto'  # Auto-detect controller
  deadzone: 5          # Stick deadzone percentage

drive:
  max_speed: 200       # Maximum speed (0-255)
  speed_scale: 1.0     # Overall speed multiplier
  steering_sensitivity: 1.0

servo:
  enabled: true
  servos:
    - channel: 0
      positions:
        neutral: 127
        position1: 50    # Button A
        position2: 200   # Button B

safety:
  input_timeout: 5     # Stop after 5s no input
  stop_on_disconnect: true
```

## Usage

### Manual Operation

Run directly for testing:
```bash
python3 rvr_controller.py
```

Press `Ctrl+C` to stop.

### Auto-start Service

Enable auto-start on boot:
```bash
sudo systemctl enable rvr-controller.service
sudo systemctl start rvr-controller.service
```

Check status:
```bash
sudo systemctl status rvr-controller.service
```

View logs:
```bash
sudo journalctl -u rvr-controller.service -f
```

Stop service:
```bash
sudo systemctl stop rvr-controller.service
```

Disable auto-start:
```bash
sudo systemctl disable rvr-controller.service
```

## Control Scheme

### Driving
- **Right Trigger (RT)**: Forward throttle (proportional 0-255)
- **Left Trigger (LT)**: Reverse throttle (proportional 0-255)
- **Left Stick X-Axis**: Steering (left/right)
- **Both Triggers Pressed**: Emergency stop (cancels out)

### Servo Control (default mapping)
- **A Button**: Servo 0 to position 1
- **B Button**: Servo 0 to position 2
- **X Button**: Servo 1 to position 1
- **Y Button**: Servo 1 to position 2

## Troubleshooting

### Controller Not Detected

1. Verify controller is connected:
```bash
ls /dev/input/
```

2. Check for input events:
```bash
sudo apt-get install evtest
sudo evtest
```

3. Find your controller name and update `config.yaml` if needed

### RVR Not Responding

1. Check UART connection:
```bash
ls -l /dev/serial0
```
Should show: `/dev/serial0 -> ttyAMA0`

2. Verify user is in dialout group:
```bash
groups
```
Should include `dialout`

3. Check RVR power and battery level

4. Test UART communication:
```bash
sudo apt-get install minicom
minicom -b 115200 -o -D /dev/serial0
```

### Service Fails to Start

1. Check logs:
```bash
sudo journalctl -u rvr-controller.service -n 50
```

2. Verify permissions:
```bash
ls -l /dev/serial0 /dev/input/event*
```

3. Test manual execution:
```bash
python3 /home/pi/rvr/rvr_controller.py
```

### Performance Issues on Pi Zero

1. Use Raspberry Pi OS Lite (no desktop):
```bash
sudo raspi-config
# System Options -> Boot / Auto Login -> Console
```

2. Disable unnecessary services:
```bash
sudo systemctl disable bluetooth
sudo systemctl disable wifi-country
```

3. Reduce logging in `config.yaml`:
```yaml
logging:
  level: 'WARNING'
  log_inputs: false
  log_commands: false
```

## Finding Controller Event Codes

If using a different controller, determine event codes:

1. Install evtest:
```bash
sudo apt-get install evtest
```

2. Run evtest:
```bash
sudo evtest
```

3. Select your controller from the list

4. Press buttons and move sticks to see event codes

5. Update `config.yaml` with correct codes:
```yaml
controller:
  event_codes:
    right_trigger: 'ABS_RZ'  # Use code from evtest
    left_trigger: 'ABS_Z'
    # etc...
```

## Servo Configuration

The Sphero RVR supports up to 4 servo outputs. Configure in `config.yaml`:

```yaml
servo:
  enabled: true
  servos:
    - channel: 0          # First servo
      name: 'Gripper'
      positions:
        neutral: 127      # Center position
        position1: 50     # Open
        position2: 200    # Close

    - channel: 1          # Second servo
      name: 'Camera Pan'
      positions:
        neutral: 127
        position1: 60     # Left
        position2: 190    # Right
```

Servo values range from 0-255 (typically 127 is center/neutral).

## Architecture

```
┌─────────────────────┐
│  rvr_controller.py  │  Main application & coordination
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
┌────▼───────┐ ┌─▼──────────┐
│controller_ │ │rvr_driver. │
│input.py    │ │py          │
└────┬───────┘ └─┬──────────┘
     │           │
┌────▼───────┐ ┌─▼──────────┐
│  evdev     │ │sphero-sdk  │
│  (USB)     │ │  (UART)    │
└────┬───────┘ └─┬──────────┘
     │           │
     │           │
  [Controller] [RVR Robot]
```

## File Structure

```
rvr/
├── config.yaml              # Configuration
├── controller_input.py      # evdev controller interface
├── rvr_driver.py           # Sphero SDK wrapper
├── rvr_controller.py       # Main application
├── requirements.txt        # Python dependencies
├── rvr-controller.service  # systemd service file
├── install.sh              # Installation script
└── README.md               # This file
```

## Development

### Running in Debug Mode

Enable verbose logging:
```bash
# Edit config.yaml
logging:
  level: 'DEBUG'
  log_inputs: true
  log_commands: true

# Run manually
python3 rvr_controller.py
```

### Testing Without RVR

Comment out RVR connection in `rvr_controller.py` for controller testing:
```python
# await self.rvr.connect()  # Disable for controller-only testing
```

## Performance Characteristics

On Raspberry Pi Zero W:
- **Latency**: 20-100ms (controller input to RVR response)
- **CPU Usage**: 20-40% during active control
- **Memory Usage**: 150-250MB total
- **Suitable for**: Basic to moderate robotics control tasks

For lower latency (<10ms), consider:
- Raspberry Pi Zero 2 W (quad-core)
- PREEMPT_RT kernel patch
- Direct serial protocol (bypass SDK)

## Safety Notes

- Always test in a safe, open area
- Keep emergency stop accessible (both triggers)
- Monitor battery levels on both RVR and controller
- Set appropriate `max_speed` for your environment
- Use `input_timeout` to prevent runaway behavior

## License

[Specify your license here]

## Contributing

Contributions welcome! Please submit issues and pull requests.

## Acknowledgments

- Sphero SDK: https://github.com/sphero-inc/sphero-sdk-raspberrypi-python
- evdev library: https://python-evdev.readthedocs.io/

## Support

For issues and questions:
- Check troubleshooting section above
- Review logs: `sudo journalctl -u rvr-controller.service`
- Test components individually (controller, UART, RVR)
- Open an issue with logs and configuration
