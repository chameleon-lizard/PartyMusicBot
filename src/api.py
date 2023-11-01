import logging

import fastapi
import pydantic

from src import server
from src import utils

app = fastapi.FastAPI()

player = server.Player()
player.start()


class AddSongBaseModel(pydantic.BaseModel):
    url: str


@app.post("/add_song")
def play_song(
    add_song: AddSongBaseModel,
):
    if not utils.check_url(url=add_song.url):
        logging.error(msg=f'Incorrect URL: {add_song.url}')

        return {
            'Result': f'Incorrect URL: {add_song.url}',
        }

    try:
        song = utils.download_song(add_song.url)
    except ValueError as e:
        logging.error(msg=f'Youtube-dl returned error: {str(e)}, URL: {add_song.url}')
        return {
            'Result': f'Youtube-dl returned error: {str(e)}, URL: {add_song.url}',
        }

    try:
        player.add_song(song)
    except server.playsound.PlaysoundException as e:
        logging.error(msg=f'Playsound error: {str(e)}, Song: {song}')
        return {
            'Result': f'Playsound error: {str(e)}, Song: {song}',
        }

    return {
        'Result': song.to_dict()
    }


@app.get("/now_playing")
def now_playing():
    return player.now_playing.to_dict()


@app.get("/history")
def get_history():
    return {
        'Result': list(map(lambda _: _.to_dict(), player.history))
    }


@app.get("/check_queue")
def check_queue():
    return {
        'Result': player.queue.snapshot()
    }
