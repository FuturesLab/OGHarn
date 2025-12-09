#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

mkdir -p $SCRIPT_DIR/multiplier/install
cd $SCRIPT_DIR/multiplier &&\
wget https://github.com/trailofbits/multiplier/releases/download/e137812/multiplier-e137812.tar.xz &&\
tar -xf multiplier-e137812.tar.xz &&\
mv bin install