#!/bin/bash

source /app/env

# Clean music cache
find /app/music_cache/ -name '*.*' -mmin +59 -delete > /dev/null

# Get today's weekday
today=$(date +"%u")

# Find the corresponding link for this day
today_link=${playlists[$today - 1]}

# Sending the link to the app
curl -X 'POST' \
  "http://127.0.0.1:$API_PORT/start_party" \
  -H 'accept: application/json' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
  \"url\": \"$today_link\",
  \"host_name\": \"host\"
}"
