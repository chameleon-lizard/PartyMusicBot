import logging
import os
import requests

import telebot
from telebot.async_telebot import AsyncTeleBot

logging.basicConfig(format='%(levelname)s: %(message)s"', level=logging.INFO)

bot = AsyncTeleBot(os.environ.get('BOT_TOKEN'))


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
    response = requests.post(
        url=os.environ.get('SERVER_IP'),
        data={
            'url': f'{message.text}'
        }
    ).json()

    await bot.reply_to(
        message=message,
        text=f"{response['Result']}"
    )


@bot.message_handler(commands=['now_playing'])
async def now_playing(message: telebot.types.Message) -> None:
    response = requests.get(
        url=os.environ.get('SERVER_IP'),
    ).json()

    await bot.reply_to(
        message=message,
        text=f"{response['name']}"
    )


@bot.message_handler(commands=['history'])
async def now_playing(message: telebot.types.Message) -> None:
    response = requests.get(
        url=os.environ.get('SERVER_IP'),
    ).json()

    history_names = '\n'.join(f"{_['name']: _['url']}" for _ in response['Result'])

    await bot.reply_to(
        message=message,
        text=history_names,
    )


def start_bot() -> None:
    bot.infinity_polling()
