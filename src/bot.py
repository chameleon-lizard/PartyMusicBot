import json
import logging
import os

import dotenv
import requests
import telebot

from src import utils

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)

dotenv.load_dotenv('../venv/.env')

bot = telebot.TeleBot(
    token=f"{os.environ.get('BOT_TOKEN')}",
    parse_mode='MARKDOWN',
    threaded=True,
)

button_markup = telebot.types.ReplyKeyboardMarkup(row_width=2)
button_markup.add(telebot.types.KeyboardButton('Queue'))
button_markup.add(telebot.types.KeyboardButton('History'))
button_markup.add(telebot.types.KeyboardButton('Now playing'))
button_markup.add(telebot.types.KeyboardButton('Skip'))
button_markup.add(telebot.types.KeyboardButton('Help'))


def register_new_user(
    message: telebot.types.Message,
    user_id: str,
    username: str,
) -> bool:
    """
    Register a new user in the backend.

    :param message: Telegram message handle
    :param user_id: User id
    :param username: Username

    :return: True if user was registered, False if connection to server was not completed.
    """
    try:
        requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/register",
            data=json.dumps(
                {
                    'user_id': f'{user_id}',
                    'username': f'@{username}',
                }
            ),
        ).json()

        return True
    except requests.exceptions.ConnectionError:
        logging.info(f'Could not register user: {user_id}, @{username}')
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return False


@bot.message_handler(func=lambda message: message.text in ('/start', '/help', 'Help'))
def welcome(message: telebot.types.Message) -> None:
    """
    Handle the user's first message to the bot, sending a greeting and instructions on how to use the bot. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    logging.info(f'User: {message.from_user.id}, @{message.from_user.username} pressed "Help" or /start.')

    # Registering new user
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    # Replying with welcome message
    bot.reply_to(
        message=message,
        text="Hi there! I am a bot that can organize music queue during parties. Send a link to youtube video into "
             "the bot to put it into queue. Here are the commands: \n"
             "- Queue - check the current queue\n"
             "- History - check the history of played songs\n"
             "- Now playing - check what's playing right now, what was the last song and what is the currently "
             "selected next song\n"
             "- Skip - start a vote to skip the next song, if 1/3 of active users (rounded up) vote for skipping, "
             "the song will skip\n"
             "- `/add_song_anon` <url> - add song anonymously\n"
             "- Help - show this message.",
        reply_markup=button_markup,
    )


@bot.message_handler(func=lambda message: message.text in ('Now playing',))
def now_playing(message: telebot.types.Message) -> None:
    """
    Returns the currently playing song. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    logging.info(f'User: {message.from_user.id}, @{message.from_user.username} pressed "Now playing".')

    # Registering new user
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    # Sending a request to the server to get a currently playing song
    try:
        response = requests.get(
            url=f"http://{os.environ.get('SERVER_IP')}/now_playing",
        ).json()
    except requests.exceptions.ConnectionError:
        logging.info(f'Could not connect to server: {message.from_user.id}, @{message.from_user.username}')
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return

    # If nothing is playing
    if response['Result']['url'] is None and response['Result']['name'] is None:
        bot.reply_to(
            message=message,
            text='Nothing is playing.',
            reply_markup=button_markup,
        )

        return

    # If something is playing, sending the song info and audio
    bot.reply_to(
        message=message,
        text=utils.get_song_text(song_dict=response),
        reply_markup=button_markup,
    )

    utils.send_audio(
        path=response['Result']['song_path'],
        chat_id=message.chat.id,
        name=response['Result']['name'],
        token=os.environ.get('BOT_TOKEN'),
    )


@bot.message_handler(func=lambda message: message.text in ('History',))
def history(message: telebot.types.Message) -> None:
    """
    Returns the last 10 songs or less to user. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    logging.info(f'User: {message.from_user.id}, @{message.from_user.username} pressed "History".')

    # Registering new user
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    # Sending request to the server to get history
    try:
        response = requests.get(
            url=f"http://{os.environ.get('SERVER_IP')}/history",
        ).json()
    except requests.exceptions.ConnectionError:
        logging.info(f'Could not connect to server: {message.from_user.id}, @{message.from_user.username}')
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return

    # If the length is 0, no songs have been played yet
    if len(response['Result']) == 0:
        bot.reply_to(
            message=message,
            text='No history yet. Start playing songs to get one!',
        )

        return

    # Else getting only last 10 songs to limit the amount of spam
    song_history = response['Result'][:10]

    # Sending song info
    bot.reply_to(
        message=message,
        text='\n'.join(
            f'{idx + 1}: {utils.get_song_text(song_dict=_)}' for idx, _ in enumerate(song_history)
        ),
        reply_markup=button_markup,
    )

    # Sending individual songs
    for song in song_history:
        utils.send_audio(
            path=song['song_path'],
            chat_id=message.chat.id,
            name=song['name'],
            token=os.environ.get('BOT_TOKEN'),
        )


@bot.message_handler(func=lambda message: message.text in ('Skip',))
def skip(message: telebot.types.Message) -> None:
    """
    Starts the vote for skipping the song. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    logging.info(f'User: {message.from_user.id}, @{message.from_user.username} pressed "Skip".')

    # Registering new user
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    # Sending request to the server to skip
    try:
        response = requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/skip",
            data=json.dumps(
                {
                    'user_id': f'{message.from_user.id}',
                    'username': f'@{message.from_user.username}',
                }
            ),
        ).json()
    except requests.exceptions.ConnectionError:
        logging.info(f'Could not connect to server: {message.from_user.id}, @{message.from_user.username}')
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return

    # Replying with result
    bot.reply_to(
        message=message,
        text=response['Result'],
        reply_markup=button_markup,
    )


@bot.message_handler(func=lambda message: message.text in ('Queue',))
def queue(message: telebot.types.Message) -> None:
    """
    Shows the queue of songs. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    try:
        response = requests.get(
            url=f"http://{os.environ.get('SERVER_IP')}/check_queue",
        ).json()
    except requests.exceptions.ConnectionError:
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return

    if len(response['Result']) == 0:
        bot.reply_to(
            message=message,
            text='No queue yet. Start playing songs to get one!',
        )

        return

    bot.reply_to(
        message=message,
        text='\n'.join(
            f'{idx + 1}: {utils.get_song_text(song_dict=_)}' for idx, _ in enumerate(response['Result'])
        ),
        reply_markup=button_markup,
    )


@bot.message_handler(func=lambda message: message.text.startswith('/add_song_anon'))
def add_song_anon(message: telebot.types.Message) -> None:
    """
    Adds new song anonimously. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    url = message.text[15:]

    logging.info(f'User @{message.from_user.username} with id {message.from_user.id} anonimously added url: {url}')

    try:
        response = requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/add_song",
            data=json.dumps(
                {
                    'url': url,
                    'user': {
                        'user_id': 'Anon',
                        'username': 'Anonimous user',
                    },
                }
            ),
        ).json()
    except requests.exceptions.ConnectionError:
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return

    if isinstance(response['Result'], str):
        bot.reply_to(
            message=message,
            text=response['Result'],
            reply_markup=button_markup,
        )
    else:
        bot.reply_to(
            message=message,
            text=utils.get_song_text(song_dict=response),
            reply_markup=button_markup,
        )



@bot.message_handler(content_types=['text'])
def add_song(message: telebot.types.Message) -> None:
    """
    Adds new song. Registers new users.

    :param message: The message object received from the user.

    :return: None
    """
    if not register_new_user(
        message=message,
        user_id=message.from_user.id,
        username=message.from_user.username,
    ):
        return

    url = message.text

    logging.info(f'User @{message.from_user.username} with id {message.from_user.id} added url: {url}')

    try:
        response = requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/add_song",
            data=json.dumps(
                {
                    'url': url,
                    'user': {
                        'user_id': f'{message.from_user.id}',
                        'username': f'@{message.from_user.username}',
                    },
                }
            ),
        ).json()
    except requests.exceptions.ConnectionError:
        bot.reply_to(
            message=message,
            text='Cannot connect to server.',
            reply_markup=button_markup,
        )

        return

    if isinstance(response['Result'], str):
        bot.reply_to(
            message=message,
            text=response['Result'],
            reply_markup=button_markup,
        )
    else:
        bot.reply_to(
            message=message,
            text=utils.get_song_text(song_dict=response),
            reply_markup=button_markup,
        )


def start_bot() -> None:
    """
    Starts the bot.

    :return: None
    """
    bot.infinity_polling()
