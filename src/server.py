import concurrent.futures
import logging
import math
import queue
import threading
import time

import vlc

from src import utils

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)


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
        self.users = set()

        # Creating container which holds people who want to skip the song
        self._voters_to_skip = set()

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
            self._voters_to_skip = set()

    def skip(self, user: utils.User) -> str:
        self._voters_to_skip.add(str(user.to_dict()))

        logging.info(self._voters_to_skip)
        logging.info(len(self._voters_to_skip))
        logging.info(len(self.users))

        logging.info(len(self._voters_to_skip) >= math.floor(len(self.users) / 3))

        if len(self._voters_to_skip) >= math.floor(len(self.users) / 3):
            self.media_list.remove_index(1)

            # Some VLC black magic
            self.player.next()
            self.player.next()

            self._voters_to_skip = set()

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
