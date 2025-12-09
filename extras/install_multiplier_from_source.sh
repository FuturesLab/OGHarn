#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
# For cases where the multiplier sdk cannot be downloaded, as it requires libstdc++ version 2.38 or higher

# Build Multiplier directories
WORKSPACE_DIR="${SCRIPT_DIR}/multiplier"
mkdir -p "${WORKSPACE_DIR}/build"
mkdir -p "${WORKSPACE_DIR}/src"
mkdir -p "${WORKSPACE_DIR}/install"

# Clone Multiplier
cd "${WORKSPACE_DIR}/src"
git clone https://github.com/trailofbits/multiplier.git

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