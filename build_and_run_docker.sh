#!/bin/bash

source ./env

docker build -t pmb:server .
docker run -p "$API_PORT":"$API_PORT" -p "$VLC_PORT":"$VLC_PORT" -d pmb:server
