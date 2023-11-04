import logging
import os

import dotenv
import fastapi
import pydantic
from fastapi.templating import Jinja2Templates

from src import server
from src import utils

app = fastapi.FastAPI()

player = server.Player()
player.start()

downloader = server.Downloader()
downloader.start()

dotenv.load_dotenv('venv/.env')


class AddSongBaseModel(pydantic.BaseModel):
    url: str
    suggested_by: str


@app.post('/add_song')
def add_song(
    added_song: AddSongBaseModel,
):
    if not utils.check_url(url=added_song.url):
        logging.error(msg=f'Incorrect URL: {added_song.url}')

        return {
            'Result': f'Incorrect URL: {added_song.url}',
        }

    # If the song is already in history, using the same song
    try:
        cached_song = next((_ for _ in player.history + player.queue.snapshot() if _.url == added_song.url))
        song = utils.Song(
            url=cached_song.url,
            song_path=cached_song.song_path,
            name=cached_song.name,
            suggested_by=added_song.suggested_by,
        )
    except StopIteration:
        downloader.input_queue.put(
            (
                added_song.url,
                added_song.suggested_by,
            )
        )

        song = downloader.output_queue.get()

        if not isinstance(song, utils.Song):
            logging.error(msg=f'Youtube-dl returned error: {str(song)}, URL: {added_song.url}')
            return {
                'Result': f'Youtube-dl returned error: {str(song)}, URL: {added_song.url}',
            }

    try:
        player.queue.put(song)
    except server.playsound.PlaysoundException as e:
        logging.error(msg=f'Playsound error: {str(e)}, Song: {song}')
        return {
            'Result': f'Playsound error: {str(e)}, Song: {song}',
        }

    return {
        'Result': song.to_dict(),
    }


@app.get('/now_playing')
def now_playing():
    return {
        'Result': player.now_playing.to_dict(),
    }


@app.get('/history')
def get_history():
    return {
        'Result': list(map(lambda _: _.to_dict(), player.history)),
    }


@app.get('/check_queue')
def check_queue():
    return {
        'Result': player.queue.snapshot(),
    }


templates = Jinja2Templates(directory='templates')


@app.get('/', response_class=fastapi.responses.HTMLResponse)
def index(request: fastapi.Request):
    return templates.TemplateResponse('index.html', {'request': request, 'ip': f"http://{os.environ.get('VLC_SERVER_IP')}"})
