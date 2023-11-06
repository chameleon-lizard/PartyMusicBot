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
button_markup.add(telebot.types.KeyboardButton('Help'))


@bot.message_handler(func=lambda message: message.text in ('/start', '/help', 'Help'))
def welcome(message: telebot.types.Message) -> None:
    bot.reply_to(
        message=message,
        text="Hi there! I am a bot that can organize music queue during parties. Send a link to youtube video into "
             "the bot to put it into queue. Here are the commands: \n- "
             "Now playing - check what's playing right now, what was the last song and what is the currently "
             "selected next song \n- Queue - check the current queue\n- History - check the history of played songs\n"
             "- Help - show this message.",
        reply_markup=button_markup,
    )


@bot.message_handler(func=lambda message: message.text in ('Now playing',))
def now_playing(message: telebot.types.Message) -> None:
    try:
        response = requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/now_playing",
            data=json.dumps(
                {
                    'user_id': f'{message.from_user.id}',
                    'username': f'@{message.from_user.username}',
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

    if response['Result']['url'] is None and response['Result']['name'] is None:
        bot.reply_to(
            message=message,
            text='Nothing is playing.',
            reply_markup=button_markup,
        )

        return

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
    try:
        response = requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/history",
            data=json.dumps(
                {
                    'user_id': f'{message.from_user.id}',
                    'username': f'@{message.from_user.username}',
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

    if len(response['Result']) == 0:
        bot.reply_to(
            message=message,
            text='No history yet. Start playing songs to get one!',
        )

        return

    song_history = response['Result'][:10]

    bot.reply_to(
        message=message,
        text='\n'.join(
            f'{idx + 1}: {utils.get_song_text(song_dict=_)}' for idx, _ in enumerate(song_history)
        ),
        reply_markup=button_markup,
    )

    for song in song_history:
        utils.send_audio(
            path=song['song_path'],
            chat_id=message.chat.id,
            name=song['name'],
            token=os.environ.get('BOT_TOKEN'),
        )


@bot.message_handler(func=lambda message: message.text in ('Queue',))
def queue(message: telebot.types.Message) -> None:
    try:
        # TODO: User not created
        response = requests.post(
            url=f"http://{os.environ.get('SERVER_IP')}/check_queue",
            data=json.dumps(
                {
                    'user_id': f'{message.from_user.id}',
                    'username': f'@{message.from_user.username}',
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


@bot.message_handler(content_types=['text'])
def add_song(message: telebot.types.Message) -> None:
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
    bot.infinity_polling()
