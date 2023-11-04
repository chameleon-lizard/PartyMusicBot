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


@bot.message_handler(commands=['help', 'start'])
def welcome(message: telebot.types.Message) -> None:
    bot.reply_to(
        message=message,
        text="Hi there! I am a bot that can organize music queue during parties. Here are the commands: \n- "
             "/add_song - add a song to the queue. Alternatively, just send the link into the bot. \n- "
             "/now_playing - check what's playing right now, what was the last song and what is the currently "
             "selected next song \n- /queue - check the current queue"
    )


@bot.message_handler(func=lambda message: message.text in ('Now playing',))

@bot.message_handler(commands=['now_playing'])
def now_playing(message: telebot.types.Message) -> None:
    response = requests.get(
        url=f"http://{os.environ.get('SERVER_IP')}/now_playing",
    ).json()

    if response['Result']['url'] is None and response['Result']['name'] is None:
        bot.reply_to(
            message=message,
            text='Nothing is playing.',
        )

        return

    bot.reply_to(
        message=message,
        text=utils.get_song_text(song_dict=response),
    )

    utils.send_audio(
        path=response['Result']['song_path'],
        chat_id=message.chat.id,
        name=response['Result']['name'],
        token=os.environ.get('BOT_TOKEN'),
    )


@bot.message_handler(commands=['history'])
def history(message: telebot.types.Message) -> None:
    response = requests.get(
        url=f"http://{os.environ.get('SERVER_IP')}/history",
    ).json()

    if len(response['Result']) == 0:
        bot.reply_to(
            message=message,
            text='No history yet. Start playing songs to get one!',
        )

        return

    bot.reply_to(
        message=message,
        text='\n'.join(
            f'{idx + 1}: {utils.get_song_text(song_dict=_)}' for idx, _ in enumerate(response['Result'])
        ),
    )

    for song in response['Result']:
        utils.send_audio(
            path=song['song_path'],
            chat_id=message.chat.id,
            name=song['name'],
            token=os.environ.get('BOT_TOKEN'),
        )


@bot.message_handler(commands=['queue'])
def queue(message: telebot.types.Message) -> None:
    response = requests.get(
        url=f"http://{os.environ.get('SERVER_IP')}/check_queue",
    ).json()

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

@bot.message_handler(content_types=['text'])
def add_song(message: telebot.types.Message) -> None:
    url = message.text

    logging.info(f'User @{message.from_user.username} with id {message.from_user.id} added url: {url}')

    response = requests.post(
        url=f"http://{os.environ.get('SERVER_IP')}/add_song",
        data=json.dumps(
            {
                'url': url,
                'suggested_by': f'@{message.from_user.username}',
            }
        )
    ).json()

    bot.reply_to(
        message=message,
        text=utils.get_song_text(song_dict=response),
        reply_markup=button_markup,
    )


def start_bot() -> None:
    bot.infinity_polling()
