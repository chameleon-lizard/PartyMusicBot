import concurrent.futures
import json
import logging
import math
import queue
import random

import requests
import threading
import time

import vlc

from src import utils

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)


PLAYLIST_SLEEP_TIME = 30


class Player(threading.Thread):
    """
    Class for the backend player that manages history, queue and now playing.

    """

    def __init__(self):
        super(Player, self).__init__()

        # Creating song queue, users set and history
        self.queue = utils.SnapshotQueue()
        self.now_playing = utils.Song()
        self.history = []
        self.users = []

        # Creating container which holds people who want to skip the song
        self._voters_to_skip = list()

        # Creating VLC instance, player and playlist
        self.vlc_instance = vlc.Instance()
        self.player = vlc.MediaListPlayer()
        self.media_list = self.vlc_instance.media_list_new()

        # Creating parameter string for VLC
        self.sout = \
            ('sout=#transcode{vcodec=none,acodec=mp3,ab=128,channels=2,samplerate=44100,scodec=none}:http{mux=mp3,'
             'dst=:8080/}')

        # Creating and adding the silence between the songs so VLC will not stop streaming
        silence = self.vlc_instance.media_new(
            f"file://{utils.pathlib.Path('resources/silence.mp3').absolute()}",
            self.sout,
        )
        self.player.set_media_list(self.media_list)
        self.media_list.add_media(silence)

    def run(self) -> None:
        while True:
            if self.queue.empty():
                self.player.play()
                time.sleep(1)
                continue

            song = self.queue.get_nowait()

            logging.info(f'Playing song: {song.name}')

            self.now_playing = song
            self.history.append(song)

            mrl = f'file://{song.song_path.absolute()}'

            m = self.vlc_instance.media_new(mrl, self.sout)
            self.media_list.add_media(m)
            self.player.play()

            while self.player.is_playing():
                time.sleep(1)

            self.media_list.remove_index(1)
            self.now_playing = utils.Song()
            self._voters_to_skip = list()

    def skip(self) -> None:
        self.media_list.remove_index(1)

        # Some VLC black magic
        self.player.next()
        self.player.next()

        self._voters_to_skip = list()

    def add_voter(self, user: utils.User) -> str:
        if user not in self._voters_to_skip:
            self._voters_to_skip.append(user)

        if len(self._voters_to_skip) >= math.floor(len(self.users) / 3):
            self.skip()
            return 'Skipping song...'

        return f'Votes: {len(self._voters_to_skip)}/{math.floor(len(self.users) / 3) if len(self.users) > 3 else 1}'


class Downloader(threading.Thread):
    """
    Class for the backend downloader, which can download and process videos in parallel.

    Inspired by: https://stackoverflow.com/a/41654240

    """

    def __init__(self) -> None:
        super(Downloader, self).__init__()
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.pool = concurrent.futures.ProcessPoolExecutor

    def run(self) -> None:
        with self.pool() as executor:
            future_to_song = {}
            while True:
                # check for status of the futures which are currently working
                done, not_done = concurrent.futures.wait(
                    future_to_song,
                    timeout=1,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                # if there is incoming work, start a new future
                while not self.input_queue.empty():
                    # fetch an url and suggested_by from the queue
                    url, suggested_by = self.input_queue.get()

                    # Start the load operation and mark the future with its URL
                    future_to_song[executor.submit(utils.download_song, url, suggested_by)] = url

                # process any completed futures
                for future in done:
                    url = future_to_song[future]
                    try:
                        result = future.result()

                        self.output_queue.put(result)
                    except Exception as e:
                        logging.error(f'{url} generated an exception: {e}')
                        self.output_queue.put(e)

                    # remove the now completed future
                    del future_to_song[future]


class PlaylistSuggester(threading.Thread):
    """
    Class for the backend which suggests songs from a party playlist if nothing is playing.

    """

    def __init__(self, server_ip: str):
        super(PlaylistSuggester, self).__init__()

        self.host_user = utils.User()
        self.song_playlist = []
        self._server_ip = server_ip

    def run(self):
        while True:
            # If the playlist is empty, do nothing
            if not self.song_playlist:
                time.sleep(5)
                continue

            # Getting info about playback
            response = requests.get(
                url=f"http://{self._server_ip}/now_playing",
            ).json()

            # If nothing is playing, adding song via API
            if response['Result']['url'] is None and response['Result']['name'] is None:
                requests.post(
                    url=f"http://{self._server_ip}/add_song",
                    data=json.dumps(
                        {
                            'url': random.choice(self.song_playlist),
                            'user': self.host_user.to_dict(),
                        }
                    ),
                )

            time.sleep(PLAYLIST_SLEEP_TIME)

    def add_playlist(self, playlist: str, host_name: str) -> None:
        # Changing the party host name
        self.host_user = utils.User(
            username=host_name,
            user_id='not_defined',
        )

        # Creating youtube-dlp option list
        ydl_opts = {
            'outtmpl': '%(id)s%(ext)s',
            'ignoreerrors': True,
        }

        # Getting urls of videos to put in queue
        with utils.yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                result = ydl.extract_info(
                    playlist,
                    download=False,
                )  # We just want to extract the info
            except utils.yt_dlp.DownloadError:
                logging.info('Download error')

            if 'entries' in result:
                # Can be a playlist or a list of videos
                video = result['entries']

                # loops entries to grab each video_url
                for item in video:
                    logging.info(f"Found video url: {item['webpage_url']}")
                    self.song_playlist.append(item['webpage_url'])

    def delete_playlist(self):
        self.host_user = utils.User()
        self.song_playlist = []
