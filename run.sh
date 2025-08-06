#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export PCDS_CONDA_VER=6.0.1
source /reg/g/pcds/engineering_tools/latest-released/scripts/pcds_conda ""

cd $SCRIPT_DIR

python -m btms_ui.main "$@" &
