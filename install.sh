#!/bin/bash
# Installation script for Sphero RVR Controller
# For Raspberry Pi Zero W running Raspberry Pi OS

set -e

echo "=========================================="
echo "Sphero RVR Controller Installation"
echo "=========================================="
echo ""

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: This script is designed for Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if running as non-root
if [ "$EUID" -eq 0 ]; then
    echo "Please run this script as a regular user (not root)"
    echo "The script will use sudo when needed"
    exit 1
fi

# Get installation directory (current directory by default)
INSTALL_DIR=$(pwd)
echo "Installation directory: $INSTALL_DIR"
echo ""

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv python3-dev

# Install evdev system package (optional, can also install via pip)
sudo apt-get install -y python3-evdev

echo ""
echo "Configuring UART..."

# Enable UART and disable console on serial
if ! grep -q "enable_uart=1" /boot/config.txt; then
    echo "Enabling UART in /boot/config.txt..."
    echo "enable_uart=1" | sudo tee -a /boot/config.txt
else
    echo "UART already enabled"
fi

# Disable console on serial
if grep -q "console=serial0" /boot/cmdline.txt; then
    echo "Disabling console on serial..."
    sudo sed -i 's/console=serial0,115200 //g' /boot/cmdline.txt
fi

# Add user to required groups
echo ""
echo "Adding user to required groups..."
sudo usermod -a -G input,dialout $USER

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install -r requirements.txt --user

# Make Python scripts executable
echo ""
echo "Making scripts executable..."
chmod +x rvr_controller.py
chmod +x controller_input.py
chmod +x rvr_driver.py

# Setup systemd service
echo ""
echo "Setting up systemd service..."

# Update service file with current user and installation directory
SERVICE_FILE="/tmp/rvr-controller.service"
sed "s|User=pi|User=$USER|g" rvr-controller.service > $SERVICE_FILE
sed -i "s|Group=pi|Group=$USER|g" $SERVICE_FILE
sed -i "s|WorkingDirectory=/home/pi/rvr|WorkingDirectory=$INSTALL_DIR|g" $SERVICE_FILE
sed -i "s|ExecStart=/usr/bin/python3 /home/pi/rvr/rvr_controller.py /home/pi/rvr/config.yaml|ExecStart=/usr/bin/python3 $INSTALL_DIR/rvr_controller.py $INSTALL_DIR/config.yaml|g" $SERVICE_FILE

# Copy service file to systemd
sudo cp $SERVICE_FILE /etc/systemd/system/rvr-controller.service
rm $SERVICE_FILE

# Reload systemd
sudo systemctl daemon-reload

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. REBOOT your Raspberry Pi for UART changes to take effect:"
echo "   sudo reboot"
echo ""
echo "2. After reboot, verify UART is available:"
echo "   ls -l /dev/serial0"
echo ""
echo "3. Connect your Victrix BFG Pro controller via USB"
echo ""
echo "4. Test the controller manually:"
echo "   python3 $INSTALL_DIR/rvr_controller.py"
echo ""
echo "5. If everything works, enable auto-start on boot:"
echo "   sudo systemctl enable rvr-controller.service"
echo "   sudo systemctl start rvr-controller.service"
echo ""
echo "6. Check service status:"
echo "   sudo systemctl status rvr-controller.service"
echo ""
echo "7. View logs:"
echo "   sudo journalctl -u rvr-controller.service -f"
echo ""
echo "Useful commands:"
echo "  Start service:   sudo systemctl start rvr-controller.service"
echo "  Stop service:    sudo systemctl stop rvr-controller.service"
echo "  Restart service: sudo systemctl restart rvr-controller.service"
echo "  Disable service: sudo systemctl disable rvr-controller.service"
echo ""
echo "Configuration file: $INSTALL_DIR/config.yaml"
echo ""
echo "Note: You may need to log out and back in for group changes to take effect"
echo "      or run: newgrp input && newgrp dialout"
echo ""
