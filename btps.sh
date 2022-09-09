#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source /reg/g/pcds/engineering_tools/latest-released/scripts/pcds_conda ""

# cd $SCRIPT_DIR
# python -m btms_ui.bin.main "$@" &
cd /cds/group/pcds/pyps/apps/dev/pcdsdevices/pcdsdevices
pydm ui/btps.ui &
