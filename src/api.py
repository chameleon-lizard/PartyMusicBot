"""
Api for the PartyMusicBot. Supports the following endpoints

1. /add_song: Add a song to the queue. The user needs to pass the URL of the song, as well as their username and user ID
(optional).
2. /start_party: Start the party by adding a playlist. The user should provide the URL of the playlist and the host name
for it.
3. /stop_party: Stop the party by emptying the queue, clearing the history, and ending playback. The user needs to pass
their username and user ID (optional).
4. /skip: Skip a song. The user should provide their username and user ID (optional).
5. /now_playing: Get information about the currently playing song.
6. /history: Get a list of all songs played so far.
7. /register: Register a new user with the system. The user should provide their username and user ID (optional).
8. /check_queue: Get a snapshot of the current queue, including all songs that have been added but not yet played.

"""

import logging
import os

import dotenv
import fastapi
import pydantic
from fastapi import Depends, HTTPException
from fastapi import status as fastapi_status
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src import server
from src import utils


dotenv.load_dotenv('venv/.env')

app = fastapi.FastAPI()

security = HTTPBearer()

player = server.Player()
player.start()

downloader = server.Downloader()
downloader.start()

suggester = server.PlaylistSuggester(
    server_ip=os.environ.get('SERVER_IP'),
)
suggester.start()


class UserBaseModel(pydantic.BaseModel):
    """
    BaseModel for the user.

    """
    user_id: str | None = None
    username: str | None = None

    def convert_to_user(self) -> utils.User:
        """
        Converts the BaseModel into a User object.

        :return: A User object

        """
        return utils.User(
            user_id=self.user_id,
            username=self.username,
        )


class AddSongBaseModel(pydantic.BaseModel):
    """
    BaseModel for the song addition.

    """
    url: str
    user: UserBaseModel


class AddPlaylistBaseModel(pydantic.BaseModel):
    """
    BaseModel for the playlist addition.

    """
    url: str
    host_name: str


def check_user_token(
    user_token: HTTPAuthorizationCredentials,
):
    """
    Checks if the user token is the same as the admin token in the env file.

    :param user_token: User token to check

    :return: True if the user token is not the same as the admin token in the env file

    """
    return user_token != os.environ.get('ADMIN_TOKEN')


@app.post('/add_song')
def add_song(
    added_song: AddSongBaseModel,
) -> dict:
    """
    Adds a song to the player queue.

    :param added_song: The song to add

    :return: Dictionary with added song info or error message

    """
    # Checking if the url is not for Youtube/YTM
    if not utils.check_url(url=added_song.url):
        logging.error(msg=f'Incorrect URL: {added_song.url}')

        return {
            'Result': f'Error: incorrect URL: {added_song.url}',
        }

    # Checking if the url is a playlist url, since we don't want someone to send a long playlist
    if utils.check_for_playlist(url=added_song.url):
        logging.error(msg=f"URL is a playlist, won't add: {added_song.url}")

        return {
            'Result': f"Error: URL is a playlist, won't add: {added_song.url}",
        }

    # Check if the user is spamming many songs in the row
    if sum(map(lambda _: _.suggested_by.username == added_song.user.username, player.queue.snapshot())) >= 3:
        return {
            'Result': 'Too many added songs in queue. Please try again later, when your other songs have been played!'
        }

    try:
        # Checking if the song has been downloaded to add songs automatically
        cached_song = next((_ for _ in player.history + player.queue.snapshot() if _.url == added_song.url))
        song = utils.Song(
            url=cached_song.url,
            song_path=cached_song.song_path,
            name=cached_song.name,
            suggested_by=added_song.user.convert_to_user(),
        )
    except StopIteration:
        # If no songs were found, adding a task to the downloader to download a song
        downloader.input_queue.put(
            (
                added_song.url,
                added_song.user.convert_to_user(),
            )
        )

        # Getting a song from the downloader
        song = downloader.output_queue.get()

        # If yt-dlp did not download a song, it does not return the song
        if not isinstance(song, utils.Song):
            logging.error(msg=f'Youtube-dl returned error: {str(song)}, URL: {added_song.url}')
            return {
                'Result': f'Error: youtube-dl returned error: {str(song)}, URL: {added_song.url}',
            }

    # Adding a song to the queue, returning the result
    player.queue.put(song)

    return {
        'Result': song.to_dict(),
    }


@app.post('/start_party')
def start_party(
    playlist: AddPlaylistBaseModel,
    user_token: HTTPAuthorizationCredentials = Depends(security),
):
    if not check_user_token(user_token):
        raise HTTPException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            detail='Insufficient privileges for this operation',
        )

    if not utils.check_url(playlist.url):
        return {
            'Result': 'Invalid url'
        }

    suggester.add_playlist(
        playlist=playlist.url,
        host_name=playlist.host_name,
    )


@app.get('/stop_party')
def stop_party(
    user_token: HTTPAuthorizationCredentials = Depends(security)
):
    if not check_user_token(user_token):
        raise HTTPException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            detail='Insufficient privileges for this operation',
        )
    
    utils.send_history_to_all_users(
        users=player.users,
        history=player.history,
        token=os.environ.get('BOT_TOKEN'),
    )

    logging.info('Removing all users, clearing queue, playlist and history, setting now_playing to empty song.')
    player.users = []
    player.history = []
    suggester.song_playlist = []
    player.now_playing = utils.Song()
    with player.queue.mutex:
        player.queue.queue.clear()

    logging.info('Stopping playback')
    player.skip()

    return {
        'Result': 'Party ended!'
    }


@app.post('/skip')
def skip(user: UserBaseModel):
    if user.convert_to_user() not in player.users:
        return {
            'Result': 'User not in system. Use Start button to register!'
        }

    res = player.add_voter(user.convert_to_user())
    return {
        'Result': f'{res}',
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


@app.post('/register')
def register(user: UserBaseModel):
    if user.convert_to_user() not in player.users:
        player.users.append(user.convert_to_user())
        logging.info(f'Registered new user: {user.convert_to_user().to_dict()}')

    return {
        'Result': 'Success!',
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
