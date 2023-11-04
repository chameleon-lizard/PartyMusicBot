import dataclasses
import json
import logging
import pathlib
import queue
import re
import shutil

import requests
import yt_dlp

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)


@dataclasses.dataclass
class Song:
    url: str | None = None
    song_path: pathlib.Path | None = None
    name: str | None = None
    suggested_by: str | None = None

    def to_dict(self) -> dict:
        return {
            'url': self.url,
            'song_path': str(self.song_path),
            'name': self.name,
            'suggested_by': self.suggested_by,
        }

    def __str__(self):
        return json.dumps(self.to_dict())


class SnapshotQueue(queue.Queue):
    def snapshot(self) -> list:
        with self.mutex:
            return list(self.queue)


def check_url(url: str) -> bool:
    youtube_url_regex_pattern = r'^(https?\:\/\/)?((www\.|music\.)?youtube\.com|youtu\.be)\/.+$'
    return re.match(pattern=youtube_url_regex_pattern, string=url) is not None


def download_song(url: str, suggested_by: str) -> Song:
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'outtmpl': '%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logging.info(msg=f'Downloading video: {url}')

        error_code = ydl.download([url])
        song_info = [ydl.extract_info(url, download=False)][0]

        shutil.move(f"{song_info['id']}.mp3", f"music_cache/{song_info['id']}.mp3")
        song_path = pathlib.Path(__file__).parent.parent / pathlib.Path(f"music_cache/{song_info['id']}.mp3")

        if error_code != 0:
            raise ValueError(f'Youtube download error: Error code {error_code}.')

        video = Song(
            url=url,
            song_path=song_path,
            name=song_info['title'],
            suggested_by=suggested_by,
        )

        return video


def send_audio(path: pathlib.Path | str, chat_id: int, name: str, token: str) -> None:
    with open(path, 'rb') as audio:
        payload = {
            'chat_id': chat_id,
            'title': name,
            'parse_mode': 'HTML'
        }
        files = {
            'audio': audio.read(),
        }
        requests.post(
            f"https://api.telegram.org/bot{token}/sendAudio",
            data=payload,
            files=files
        ).json()


def get_song_text(song_dict: dict) -> str:
    if 'Result' in song_dict:
        song_dict = song_dict['Result']

    suggested_by = song_dict['suggested_by'].replace('_', r'\_')
    return f"[{song_dict['name']}]({song_dict['url']}) - suggested by {suggested_by}"
