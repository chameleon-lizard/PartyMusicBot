import asyncio
import queue
import threading

import playsound

from src import utils


class Player(threading.Thread):
    """
    Class for the backend player that manages history, queue and now playing.

    """

    def __init__(self):
        super(Player, self).__init__()
        self.queue = queue.Queue()
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
