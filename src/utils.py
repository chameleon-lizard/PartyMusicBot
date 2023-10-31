import dataclasses
import json
import logging
import pathlib
import re
import shutil
import queue

import yt_dlp

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)


@dataclasses.dataclass
class Song:
    url: str | None = None
    song_path: pathlib.Path | None = None
    name: str | None = None

    def to_dict(self) -> dict:
        return {
            'url': self.url,
            'song_path': str(self.song_path),
            'name': self.name,
        }

    def __str__(self):
        return json.dumps(self.to_dict())


class SnapshotQueue(queue.Queue):
    def snapshot(self) -> list:
        with self.mutex:
            return list(self.queue)


def check_url(url: str) -> bool:
    youtube_url_regex_pattern = r'^(https?\:\/\/)?((www\.)?youtube\.com|youtu\.be)\/.+$'
    return re.match(pattern=youtube_url_regex_pattern, string=url) is not None


def download_song(url: str) -> Song:
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
        )

        return video
