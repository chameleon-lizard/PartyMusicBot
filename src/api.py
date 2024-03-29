"""
Api for the PartyMusicBot. Supports the following endpoints

1. /add_song: Add a song to the queue. The user needs to pass the URL of the song, as well as their username and user ID
(optional).
2. /start_party: Start the party by adding a playlist. The user should provide the URL of the playlist and the host name
for it.
3. /stop_party: Stop the party by emptying the queue, clearing the history, and ending playback. The user needs to pass
their username and user ID (optional).
4. /ban_user: Ban the user
5. /skip: Skip a song. The user should provide their username and user ID (optional).
6. /now_playing: Get information about the currently playing song.
7. /history: Get a list of all songs played so far.
8. /register: Register a new user with the system. The user should provide their username and user ID (optional).
9. /check_queue: Get a snapshot of the current queue, including all songs that have been added but not yet played.

"""
import json
import logging
import os

import dotenv
import requests
import fastapi
import pydantic
from fastapi import Depends, HTTPException
from fastapi import status as fastapi_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates

from src import server
from src import utils


logging.basicConfig(format='[%(threadName)s] %(levelname)s: %(message)s"', level=logging.INFO)

dotenv.load_dotenv('env')

app = fastapi.FastAPI()

security = HTTPBearer()

player = server.Player()
player.start()

downloader = server.Downloader()
downloader.start()

suggester = server.PlaylistSuggester(
    server_ip=f"{os.environ.get('SERVER_IP')}:{os.environ.get('API_PORT')}",
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
        try:
            is_banned = next(
                (_.is_banned for _ in player.users if _.user_id == self.user_id and _.username == '@' + self.username)
            )
        except StopIteration:
            is_banned = False
        return utils.User(
            user_id=self.user_id,
            username=self.username,
            is_banned=is_banned,
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


def check_user_for_ban(
    user: UserBaseModel,
) -> bool:
    """
    Checks if the user is banned.

    :param user: The BaseModel for the user to check

    :return: is_banned field of User with the same credentials

    """
    try:
        return next(
            (_.is_banned for _ in player.users if _.user_id == user.user_id and _.username == '@' + user.username)
        )
    except StopIteration:
        return False


def check_user_token(
    user_token: HTTPAuthorizationCredentials,
):
    """
    Checks if the user token is the same as the admin token in the env file.

    :param user_token: User token to check

    :return: True if the user token is not the same as the admin token in the env file

    """
    return user_token != os.environ.get('ADMIN_TOKEN')


@app.post('/add_song_anon')
def add_song_anon(
    added_song: AddSongBaseModel,
) -> dict:
    """
    Anonymously adds a song to the player queue.

    :param added_song: The song to add

    :return: Dictionary with added song info or error message

    """
    if check_user_for_ban(added_song.user):
        logging.error(msg=f'Banned user: {added_song.user} tried to add song.')

        return {
            'Result': f'User banned, song not added.'
        }
    
    try:
        return requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}:{os.environ.get('API_PORT')}/add_song",
            data=json.dumps(
                {
                    'url': added_song.url,
                    'user': {
                        'user_id': f'Anon',
                        'username': f'Anonymous user',
                    },
                }
            ),
        ).json()
    except requests.exceptions.ConnectionError:
        return {
            'Result': f'Could not connect to server',
        }


@app.post('/add_song')
def add_song(
    added_song: AddSongBaseModel,
) -> dict:
    """
    Adds a song to the player queue.

    :param added_song: The song to add

    :return: Dictionary with added song info or error message

    """
    if check_user_for_ban(added_song.user):
        logging.error(msg=f'Banned user: {added_song.user} tried to add song.')

        return {
            'Result': f'User banned, song not added.'
        }

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
        logging.info(f'User @{added_song.user.convert_to_user().to_dict()} tried to add fourth song.')
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
        logging.info(f'Song {song.name} found in cache: "{song.song_path}"')
    except StopIteration:
        logging.info(f'Song not found, adding url "{added_song.url}" to downloader.')

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
    logging.info(f'Song {song.name} added to queue.')
    player.queue.put(song)

    return {
        'Result': song.to_dict(),
    }


@app.post('/start_party')
def start_party(
    playlist: AddPlaylistBaseModel,
    user_token: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Start party endpoint.

    :param playlist: Party playlist
    :param user_token: User token for basic security

    :return: Dictionary with result status

    """
    logging.info(f'Attempt to start party: {playlist.host_name}, {playlist.url}, {user_token.model_dump_json()}')
    # If not authenticated
    if not check_user_token(user_token):
        raise HTTPException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            detail='Insufficient privileges for this operation',
        )

    # If the link is incorrect
    if not utils.check_url(playlist.url):
        return {
            'Result': 'Invalid url'
        }

    # Adding the playlist to the suggester and returning success
    suggester.add_playlist(
        playlist=playlist.url,
        host_name=playlist.host_name,
    )

    return {
        'Result': 'Success'
    }


@app.get('/stop_party')
def stop_party(
    user_token: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    End party endpoint.

    :param user_token: User token for basic security

    :return: Dictionary with result status

    """
    logging.info(f'Attempt to stop party: {user_token.model_dump_json()}')
    # If not authenticated
    if not check_user_token(user_token):
        raise HTTPException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            detail='Insufficient privileges for this operation',
        )

    # Sending history to everyone
    utils.send_history_to_all_users(
        users=player.users,
        history=player.history,
        token=os.environ.get('BOT_TOKEN'),
    )

    # Restoring the initial settings
    logging.info('Removing all users, clearing queue, playlist and history, setting now_playing to empty song.')
    player.users = []
    player.history = []
    suggester.song_playlist = []
    player.now_playing = utils.Song()
    with player.queue.mutex:
        player.queue.queue.clear()

    # Stopping the playback and returning the results
    logging.info('Stopping playback')
    player.skip()

    return {
        'Result': 'Party ended!'
    }


@app.post('/ban_user')
def ban_user(
    user_info: UserBaseModel,
    user_token: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Ban user endpoint.

    :param user_info: User info
    :param user_token: User token for basic security

    :return: Dictionary with result status

    """
    logging.info(f'Attempting to ban a user: {user_info.user_id}, @{user_info.username}, {user_token.model_dump_json()}')

    user_info = user_info.convert_to_user()
    # If not authenticated
    if not check_user_token(user_token):
        raise HTTPException(
            status_code=fastapi_status.HTTP_403_FORBIDDEN,
            detail='Insufficient privileges for this operation',
        )

    # Registering a user in case they were not registered yet. Motivation: can create a list of banned users and ban
    # them right after the party start
    utils.send_register_request(
        user_id=user_info.user_id,
        username=user_info.username,
    )

    for usr in player.users:
        if usr.username == user_info.username and usr.user_id == user_info.user_id:
            usr.is_banned = True

    return {
        'Result': 'Success'
    }


@app.post('/skip')
def skip(user: UserBaseModel) -> dict:
    """
    Skip song endpoint.

    :param user: UserBaseModel of user, who voted for skipping

    :return: Dictionary with results

    """
    # If not registered
    if user.convert_to_user() not in player.users:
        logging.info(f'User {user.convert_to_user()} voted for skipping the song, but was unregistered.')
        return {
            'Result': 'User not in system. Use Start button to register!'
        }

    if check_user_for_ban(user):
        logging.error(msg=f'Banned user: {user} tried to skip song.')

        return {
            'Result': f'User banned, song not added.'
        }

    # Adding a voter to player class and returning results
    logging.info(f'User {user.convert_to_user()} voted for skipping the song!')
    res = player.add_voter(user.convert_to_user())
    return {
        'Result': f'{res}',
    }


@app.get('/now_playing')
def now_playing() -> dict:
    """
    Returns currently playing song info.

    :return: Dictionary with results

    """
    return {
        'Result': player.now_playing.to_dict(),
    }


@app.get('/history')
def get_history() -> dict:
    """
    Returns history of played songs.

    :return: Dictionary with results

    """
    return {
        'Result': list(map(lambda _: _.to_dict(), player.history)),
    }


@app.post('/register')
def register(user: UserBaseModel) -> dict:
    """
    Register new user.

    :param user: BaseModel of user to register

    :return: Dictionary with results

    """
    if user.convert_to_user() not in player.users:
        player.users.append(user.convert_to_user())
        logging.info(f'Registered new user: {user.convert_to_user().to_dict()}')

    return {
        'Result': 'Success!',
    }


@app.get('/check_queue')
def check_queue() -> dict:
    """
    Returns current queue of songs.

    :return: Dictionary with results

    """
    return {
        'Result': player.queue.snapshot(),
    }


templates = Jinja2Templates(directory='templates')


@app.get('/', response_class=fastapi.responses.HTMLResponse)
def index(request: fastapi.Request) -> fastapi.responses.HTMLResponse:
    """
    Renders index page with user player.

    :param request: Request object

    :return: HTML page with user player

    """
    return templates.TemplateResponse(
        'index.html', {'request': request, 'ip': f"http://{os.environ.get('VLC_SERVER_IP')}:{os.environ.get('VLC_PORT')}"}
    )
