#!/usr/bin/env bash

if [ ! -d ".venv" ]; then
    echo "venv가 없어서 세팅 시작"

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    echo "venv가 있어서 이미 세팅된거 같은데요?"
    source .venv/bin/activate
fi
