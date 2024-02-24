#!/bin/bash

source ./env

uvicorn src.api:app --host 0.0.0.0 --port "$API_PORT" &
python3 main.py
