#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PARENT_DIR=$(dirname "$SCRIPT_DIR")/src

# add Multiplier, AFL++, and OGHarn to the path
export MULT_PATH=$SCRIPT_DIR/multiplier/install/bin
export AFL_PATH=$SCRIPT_DIR/AFLplusplus
export PATH=$PATH:$MULT_PATH:$AFL_PATH:$PARENT_DIR

# activate the virtual environment and install the necessary packages
source $SCRIPT_DIR/multiplier/install/bin/activate
pip install -Iv cfile==0.2.0
pip install PyYAML
