#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

pixi run --as-is pydm "${SCRIPT_DIR}/btms_ui/ui/btps/btps.ui"
