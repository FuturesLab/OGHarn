#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

sudo apt install curl

# Add kitware's repo GPG key to the system for authentication
curl -sSL https://apt.kitware.com/keys/kitware-archive-latest.asc | \
    gpg --dearmor - | \
    sudo tee /etc/apt/trusted.gpg.d/kitware.gpg
sudo apt-add-repository "deb https://apt.kitware.com/ubuntu/ $(lsb_release -cs) main"
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 6AF7F09730B3F0A4


# # Add deadsnakes repo to apt so python3.12 can be installed
sudo add-apt-repository ppa:deadsnakes/ppa

# Installing dependencies
apt-get update && apt-get install -y \
    build-essential \
    ninja-build \
    cmake \
    graphviz \
    xdot \
    python3.12-dev \
    python3.12-venv \
    python3.10-dev \
    python3.10-venv \
    kitware-archive-keyring \
    bear \
    lld \
    llvm \
    libzstd-dev

REQUIRED_GLIBC="2.38"
INSTALLED_GLIBC=$(ldd --version | head -n1 | awk '{print $NF}')

if [ "$(printf '%s\n' "$REQUIRED_GLIBC" "$INSTALLED_GLIBC" | sort -V | head -n1)" != "$REQUIRED_GLIBC" ]; then
    echo "Building Multiplier from source:"
    . install_multiplier_from_source.sh
else
  echo "Installing Multiplier's SDK:"
  . install_multiplier_sdk.sh 
fi

# Clone and build AFLplusplus
cd "${SCRIPT_DIR}" && git clone https://github.com/AFLplusplus/AFLplusplus.git
cd "${SCRIPT_DIR}/AFLplusplus" && make all -j12 && cd "${SCRIPT_DIR}"

# Set up virtual environment
python3.12 -m venv .venv
