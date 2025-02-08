#!/bin/bash

echo "Installing MetaTrader5 dependencies..."

# Install MetaTrader5 dependencies here, e.g., using apt-get or other package managers
apt-get update
apt-get install -y wget libgdk-pixbuf2.0-0 libnss3 libxss1 libasound2

# Install MetaTrader5 Python library
pip install MetaTrader5
