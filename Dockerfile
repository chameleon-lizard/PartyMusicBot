FROM python:3.11-slim

WORKDIR /app
COPY src /app/src
COPY resources /app/resources
COPY templates /app/templates
COPY main.py /app/main.py
COPY env /app/env
COPY requirements.txt /app/requirements.txt
RUN mkdir /app/music_cache
RUN pip install -r requirements.txt
RUN apt-get update && apt-get install vlc ffmpeg cron curl -y
RUN crontab -l | { cat; echo "15 00 * * * bash /app/src/start_new_party.sh"; } | crontab -

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["/app/entrypoint.sh"]
