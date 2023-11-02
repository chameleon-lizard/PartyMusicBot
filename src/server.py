import asyncio
import concurrent.futures
import logging
import queue
import threading

import playsound

from src import utils

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)


class Player(threading.Thread):
    """
    Class for the backend player that manages history, queue and now playing.

    """

    def __init__(self):
        super(Player, self).__init__()
        self.queue = utils.SnapshotQueue()
        self.now_playing = utils.Song()
        self.history = []

        self._loop = asyncio.new_event_loop()
        self._lock = asyncio.Lock()
        self._background_tasks = set()

    async def _play_song(self, song: utils.Song) -> None:
        async with self._lock:
            self.now_playing = song
            playsound.playsound(
                sound=song.song_path.absolute(),
                block=True,
            )
            self.history.append(song)

    async def _asyncio_event_loop(self) -> None:
        while True:
            if self.queue.empty():
                await asyncio.sleep(1)
                continue

            song = self.queue.get_nowait()

            task = asyncio.create_task(
                self._play_song(song=song),
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    def add_song(self, song: utils.Song) -> None:
        self.queue.put(song)

    def run(self) -> None:
        self._loop.run_until_complete(self._asyncio_event_loop())


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
