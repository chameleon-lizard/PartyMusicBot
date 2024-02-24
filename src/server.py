"""
Server module, which contains Player, Downloader and PlaylistSuggester classes.

"""

import concurrent.futures
import json
import logging
import math
import os
import queue
import random
import threading
import time

import dotenv
import requests
import vlc

from src import utils

logging.basicConfig(format='[%(threadName)s] %(levelname)s: %(message)s"', level=logging.INFO)

dotenv.load_dotenv('env')


PLAYLIST_SLEEP_TIME = 30


class Player(threading.Thread):
    """
    Class for the backend player that manages history, queue and song skipping.

    """

    def __init__(self):
        super(Player, self).__init__()

        self.name = 'Player'

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
             'dst=:' + os.environ.get('VLC_PORT') + '/}')

        # Creating and adding the silence between the songs so VLC will not stop streaming
        silence = self.vlc_instance.media_new(
            f"file://{utils.pathlib.Path('resources/silence.mp3').absolute()}",
            self.sout,
        )
        self.player.set_media_list(self.media_list)
        self.media_list.add_media(silence)

    def run(self) -> None:
        """
        Starts the player thread.

        :return: None

        """
        logging.info('Player started.')
        while True:
            # Dirty hack to wait for songs
            if self.queue.empty():
                self.player.play()
                time.sleep(1)
                continue

            # Getting the song to play
            song = self.queue.get_nowait()

            logging.info(f'Playing song: {song.name}')

            # Adding song to history and to now_playing
            self.now_playing = song
            self.history.append(song)

            # Adding the song to VLC media list and starting the playback
            mrl = f'file://{song.song_path.absolute()}'

            m = self.vlc_instance.media_new(mrl, self.sout)
            self.media_list.add_media(m)
            self.player.play()

            # Dirty hack for waiting until the end of the song
            while self.player.is_playing():
                time.sleep(1)

            # Removing the song from VLC media list, setting default song to now_playing, clearing the skip voters list
            self.media_list.remove_index(1)
            self.now_playing = utils.Song()
            self._voters_to_skip = list()

    def skip(self) -> None:
        """
        Skips the current playing song

        :return: None

        """
        logging.info('Skipping song...')
        self.media_list.remove_index(1)

        # Some VLC black magic
        self.player.next()
        self.player.next()

        self._voters_to_skip = list()

    def add_voter(self, user: utils.User) -> str:
        """
        Adds voter for skipping.

        :param user: User that voted for skipping current song

        :return: None

        """
        if user not in self._voters_to_skip:
            self._voters_to_skip.append(user)

        # Only skip if 1/3 of the people voted to skip the song
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

        self.name = 'Downloader'

        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.pool = concurrent.futures.ProcessPoolExecutor

    def run(self) -> None:
        """
        Runs the downloader thread.

        :return: None

        """
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

                    logging.info(f'User {suggested_by} added song to the downloader queue: {url}')

                    # Start the load operation and mark the future with its URL
                    future_to_song[executor.submit(utils.download_song, url, suggested_by)] = url

                # process any completed futures
                for future in done:
                    url = future_to_song[future]
                    try:
                        result = future.result()

                        logging.info(f'Song {url} successfully downloaded.')

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

        self.name = 'PlaylistSuggester'

        self.host_user = utils.User()
        self.song_playlist = []
        self._server_ip = server_ip

    def run(self):
        """
        Runs the PlaylistSuggester thread.

        :return: None

        """
        while True:
            # If the playlist is empty, do nothing
            if not self.song_playlist:
                time.sleep(5)
                continue

            # Getting info about playback
            response = requests.get(
                url=f"http://{self._server_ip}/now_playing",
            ).json()

            # If nothing is playing, adding a song via API
            if response['Result']['url'] is None and response['Result']['name'] is None:
                song = random.choice(self.song_playlist)
                logging.info(f'Adding song {song} from the party playlist.')

                requests.post(
                    url=f"http://{self._server_ip}/add_song",
                    data=json.dumps(
                        {
                            'url': song,
                            'user': self.host_user.to_dict(),
                        }
                    ),
                )

            time.sleep(PLAYLIST_SLEEP_TIME)

    def add_playlist(self, playlist: str, host_name: str) -> None:
        """
        Adds a new playlist to the suggester.

        :param playlist: An url for the playlist
        :param host_name: Name of the host of the party

        :return: None

        """
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
                    try:
                        logging.info(f"Found video url: {item['webpage_url']}")
                        self.song_playlist.append(item['webpage_url'])
                    except TypeError:
                        continue

    def delete_playlist(self):
        """
        Clears the playlist.

        :return: None

        """
        self.host_user = utils.User()
        self.song_playlist = []
