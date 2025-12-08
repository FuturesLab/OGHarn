#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Get clang-18
wget https://apt.llvm.org/llvm.sh
chmod u+x llvm.sh
sudo ./llvm.sh 18

sudo apt install curl

# Add kitware's repo GPG key to the system for authentication
curl -sSL https://apt.kitware.com/keys/kitware-archive-latest.asc | \
    gpg --dearmor - | \
    sudo tee /etc/apt/trusted.gpg.d/kitware.gpg
sudo apt-add-repository "deb https://apt.kitware.com/ubuntu/ $(lsb_release -cs) main"
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 6AF7F09730B3F0A4


# Add deadsnakes repo to apt so python3.12 can be installed
sudo add-apt-repository ppa:deadsnakes/ppa

# Installing dependencies
apt-get update && apt-get install -y \
    build-essential \
    ninja-build \
    cmake \
    graphviz \
    xdot \
    clang-18 \
    python3.12-dev \
    python3.12-venv \
    kitware-archive-keyring \
    bear \
    lld \
    llvm \
    libzstd-dev


# Build Multiplier directories
WORKSPACE_DIR="${SCRIPT_DIR}/multiplier"
mkdir -p "${WORKSPACE_DIR}/build"
mkdir -p "${WORKSPACE_DIR}/src"
mkdir -p "${WORKSPACE_DIR}/install"

# Create a new venv for Multiplier's Python API
if [[ ! -f "${WORKSPACE_DIR}/install/bin/activate" ]]; then
  python3.12 -m venv "${WORKSPACE_DIR}/install"
fi
source "${WORKSPACE_DIR}/install/bin/activate"

# Clone Multiplier
cd "${WORKSPACE_DIR}/src"
git clone https://github.com/trailofbits/multiplier.git &&\
git checkout 1705339e24058cdb096a9a921d3fc99b52ab9a78

# Build Multiplier
cmake \
-DCMAKE_BUILD_TYPE=Release \
-DCMAKE_INSTALL_PREFIX="${WORKSPACE_DIR}/install" \
-DCMAKE_LINKER_TYPE=LLD \
-DCMAKE_C_COMPILER="$(which clang-18)" \
-DCMAKE_CXX_COMPILER="$(which clang++-18)" \
-DMX_ENABLE_INSTALL=ON \
-DMX_ENABLE_PYTHON_BINDINGS=ON \
-DLLVM_CONFIG=/usr/bin/llvm-config-18 \
-DLLVM_DIR=/usr/lib/llvm-18/lib/cmake/llvm/ \
-DCMAKE_LINKER=$(which lld-18) \
-GNinja \
"${WORKSPACE_DIR}/src/multiplier"

ninja install

# Clone and build AFLplusplus
cd "${SCRIPT_DIR}" && git clone https://github.com/AFLplusplus/AFLplusplus.git
cd "${SCRIPT_DIR}/AFLplusplus" && make all -j12 && cd "${SCRIPT_DIR}"
