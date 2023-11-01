import json
import logging
import os

import dotenv
import requests
import telebot
from telebot.async_telebot import AsyncTeleBot

from src import utils

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)

dotenv.load_dotenv('../venv/.env')

bot = AsyncTeleBot(
    token=f"{os.environ.get('BOT_TOKEN')}",
    parse_mode='MARKDOWN',
)


@bot.message_handler(commands=['help', 'start'])
async def welcome(message: telebot.types.Message) -> None:
    await bot.reply_to(
        message=message,
        text="Hi there! I am a bot that can organize music queue during parties. Here are the commands: \n- "
             "/add_song - add a song to the queue. Alternatively, just send the link into the bot. \n- "
             "/now_playing - check what's playing right now, what was the last song and what is the currently "
             "selected next song \n- /queue - check the current queue"
    )


@bot.message_handler(commands=['add_song'])
async def add_song(message: telebot.types.Message) -> None:
    url = message.text[10:]

    logging.info(f'User @{message.from_user.username} with id {message.from_user.id} added url: {url}')

    response = requests.post(
        url=f"http://{os.environ.get('SERVER_IP')}/add_song",
        data=json.dumps(
            {
                'url': url
            }
        )
    ).json()

    await bot.reply_to(
        message=message,
        text=utils.get_song_text(song_dict=response),
    )


@bot.message_handler(commands=['now_playing'])
async def now_playing(message: telebot.types.Message) -> None:
    response = requests.get(
        url=f"http://{os.environ.get('SERVER_IP')}/now_playing",
    ).json()

    if response['Result']['url'] is None and response['Result']['name'] is None:
        await bot.reply_to(
            message=message,
            text='Nothing is playing.',
        )

        return

    await bot.reply_to(
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
async def history(message: telebot.types.Message) -> None:
    response = requests.get(
        url=f"http://{os.environ.get('SERVER_IP')}/history",
    ).json()

    if len(response['Result']) == 0:
        await bot.reply_to(
            message=message,
            text='No history yet. Start playing songs to get one!',
        )

        return

    logging.info(response['Result'])

    history_names = [_['name'] for _ in response['Result']]
    history_paths = [_['song_path'] for _ in response['Result']]
    history_url = [_['url'] for _ in response['Result']]

    await bot.reply_to(
        message=message,
        text='\n\n'.join(
            f'{idx + 1}: [{name}]({url})' for idx, (name, url) in enumerate(zip(history_names, history_url))
            ),
    )

    for path, name in zip(history_paths, history_names):
        utils.send_audio(
            path=path,
            chat_id=message.chat.id,
            name=name,
            token=os.environ.get('BOT_TOKEN'),
        )


async def start_bot() -> None:
    await bot.infinity_polling()
