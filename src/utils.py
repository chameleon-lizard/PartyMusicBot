"""
Utils module with functions, used in bot, server and api.

"""

import dataclasses
import json
import logging
import pathlib
import queue
import re
import shutil

import requests
import yt_dlp

logging.basicConfig(format='[%(threadName)s] %(levelname)s: %(message)s"', level=logging.INFO)


@dataclasses.dataclass
class User:
    """
    Dataclass for user info.

    """
    user_id: str | None = None
    username: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """
        Method that converts class to a dictionary with user info.

        """
        return {
            'user_id': self.user_id,
            'username': self.username,
        }


@dataclasses.dataclass
class Song:
    """
    Dataclass for song info.

    """
    url: str | None = None
    song_path: pathlib.Path | None = None
    name: str | None = None
    suggested_by: User | None = None

    def to_dict(self) -> dict:
        """
        Method that converts class to a dictionary with user info.

        """
        return {
            'url': self.url,
            'song_path': str(self.song_path),
            'name': self.name,
            'suggested_by': self.suggested_by.to_dict() if self.suggested_by is not None else User().to_dict(),
        }

    def __str__(self):
        return json.dumps(self.to_dict())


class SnapshotQueue(queue.Queue):
    """
    Custom queue class, which can return a snapshot of the queue items. Needed, since queues are synchronized.

    """
    def snapshot(self) -> list:
        """
        Method that returns a snapshot of the queue items.

        """
        with self.mutex:
            return list(self.queue)


def check_url(url: str) -> bool:
    """
    Checks if the url is a valid Youtube/Youtube Music link.

    :param url: Youtube url of the song to download

    :return: True if url is a playlist url
    
    """
    youtube_url_regex_pattern = r'^(https?\:\/\/)?((www\.|music\.)?youtube\.com|youtu\.be)\/.+$'
    return re.match(pattern=youtube_url_regex_pattern, string=url) is not None


def check_for_playlist(url: str) -> bool:
    """
    Checks if the url is a playlist link.

    :param url: Youtube url of the song to download

    :return: True if url is a playlist url

    """
    return any(map(lambda _: _ in url, ['list',]))


def download_song(url: str, suggested_by: User) -> Song:
    """
    Function, which downloads the song from the Youtube via yt_dlp. It does this by first downloading the song to cwd
    and then moving it into the music_cache folder.

    :param url: Youtube url of the song to download
    :param suggested_by: User, who suggested the song

    :return: Song object

    """
    # Defining yt_dlp options
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'outtmpl': '%(id)s.%(ext)s',
        'ignoreerrors': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Downloading video
        logging.info(msg=f'Downloading video: {url}, user: {suggested_by}')

        error_code = ydl.download([url])
        song_info = [ydl.extract_info(url, download=False)][0]

        # Moving the file to the music cache
        new_title = ''.join('_' if not _.isalnum() else _ for _ in song_info['title'])
        shutil.move(f"{song_info['id']}.mp3", f"music_cache/{new_title}.mp3")
        song_path = pathlib.Path(__file__).parent.parent / pathlib.Path(f"music_cache/{new_title}.mp3")

        if error_code != 0:
            raise ValueError(f'Youtube download error: Error code {error_code}.')

        # Creating the Song object
        video = Song(
            url=url,
            song_path=song_path,
            name=song_info['title'],
            suggested_by=suggested_by,
        )

        return video


def get_song_text(song_dict: dict) -> str:
    """
    Formats the text for the bot to send.

    :param song_dict: Dictionary with song info

    :return: Text to send to user

    """
    if 'Result' in song_dict:
        song_dict = song_dict['Result']

    suggested_by = song_dict['suggested_by']['username'].replace('_', r'\_')
    return f"[{song_dict['name']}]({song_dict['url']}) - suggested by {suggested_by}"


def send_history_to_all_users(users: list[User], history: list[Song], token: str) -> None:
    """
    Sends history to all users.

    :param users: List of users to send history to
    :param history: List of songs that was played during this party
    :param token: Telegram bot token

    :return: None

    """
    # Formatting the history string
    if len(history) > 0:
        history_string = "Thanks for the party! Here's the song history:\n\n"

        history_string += '\n'.join(
            f'{idx + 1}: {get_song_text(song_dict=_.to_dict())}' for idx, _ in enumerate(history)
        )
    else:
        history_string = "Thanks for the party! No songs were played :("

    logging.info(f'History string: {history_string}')

    # Sending message with history to all users
    for user in users:
        logging.info(f'Sending message to {user}')

        payload = {
            'chat_id': user.user_id,
            'text': history_string,
            'parse_mode': 'Markdown',
        }

        res = requests.post(
            url=f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
        )
        logging.info(res)


def send_audio(path: pathlib.Path | str, chat_id: int, name: str, token: str) -> None:
    """
    Sends an audio via Telegram API. Needed, since Telebot does not have this function.

    :param path: Path to audio file
    :param chat_id: Telegram chat id to send the song to
    :param name: Name of the song to send
    :param token: Telegram bot token

    :return: None

    """
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
