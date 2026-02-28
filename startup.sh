#!/bin/bash -i

DIR="$( cd "$( dirname "$0" )" && pwd )"
echo "Script location: ${DIR}"

$DIR/interface/.venv/bin/python $DIR/interface/main.py
