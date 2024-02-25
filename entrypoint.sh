#!/bin/bash

source ./env

uvicorn src.api:app --host 0.0.0.0 --port "$API_PORT" &
(sleep 10; bash /app/src/start_new_party.sh) &
python3 main.py
