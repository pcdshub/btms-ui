#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source /reg/g/pcds/engineering_tools/latest-released/scripts/dev_conda ""

cd $SCRIPT_DIR

python -m btms_ui.bin.main "$@" &
