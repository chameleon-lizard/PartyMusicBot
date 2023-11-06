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


class UserBaseModel(pydantic.BaseModel):
    user_id: str | None = None
    username: str | None = None

    def convert_to_user(self) -> utils.User:
        return utils.User(
            user_id=self.user_id,
            username=self.username,
        )


class AddSongBaseModel(pydantic.BaseModel):
    url: str
    user: UserBaseModel


@app.post('/add_song')
def add_song(
    added_song: AddSongBaseModel,
):
    player.users.add(added_song.user.model_dump_json())

    if not utils.check_url(url=added_song.url):
        logging.error(msg=f'Incorrect URL: {added_song.url}')

        return {
            'Result': f'Error: incorrect URL: {added_song.url}',
        }

    # If the song is already in history, using the same song
    try:
        cached_song = next((_ for _ in player.history + player.queue.snapshot() if _.url == added_song.url))
        song = utils.Song(
            url=cached_song.url,
            song_path=cached_song.song_path,
            name=cached_song.name,
            suggested_by=added_song.user.convert_to_user(),
        )
    except StopIteration:
        downloader.input_queue.put(
            (
                added_song.url,
                added_song.user.convert_to_user(),
            )
        )

        song = downloader.output_queue.get()

        if not isinstance(song, utils.Song):
            logging.error(msg=f'Youtube-dl returned error: {str(song)}, URL: {added_song.url}')
            return {
                'Result': f'Error: youtube-dl returned error: {str(song)}, URL: {added_song.url}',
            }

    player.queue.put(song)

    return {
        'Result': song.to_dict(),
    }


@app.post('/skip')
def skip(user: UserBaseModel):
    player.users.add(user.model_dump_json())

    res = player.skip(user.convert_to_user())
    return {
        'Result': f'{res}',
    }


@app.post('/now_playing')
def now_playing(user: UserBaseModel):
    player.users.add(user.model_dump_json())

    return {
        'Result': player.now_playing.to_dict(),
    }


@app.post('/history')
def get_history(user: UserBaseModel):
    player.users.add(user.model_dump_json())

    return {
        'Result': list(map(lambda _: _.to_dict(), player.history)),
    }


@app.post('/check_queue')
def check_queue(user: UserBaseModel):
    player.users.add(user.model_dump_json())

    return {
        'Result': player.queue.snapshot(),
    }


templates = Jinja2Templates(directory='templates')


@app.get('/', response_class=fastapi.responses.HTMLResponse)
def index(request: fastapi.Request):
    return templates.TemplateResponse('index.html', {'request': request, 'ip': f"http://{os.environ.get('VLC_SERVER_IP')}"})
