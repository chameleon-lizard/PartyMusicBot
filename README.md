# PartyMusicBot

A simple bot to manage music queue during parties. API included, so you can make any frontend that you want! 

# Problem

During parties people often have only one bluetooth speaker and one phone connected to it, but many people with different
choices of music. Organising queue is a real PITA -- so I've made this bot to help me with that.

After finishing the bot, I've hosted it on my local server so it effectively became an internet radio station with
community-based song suggestions. Check it out:

- Web frontend: [chameleon-lizard.ru/radio](http://chameleon-lizard.ru:81/radio)
- Telegram bot: [@arina_party_music_bot](https://t.me/arina_party_music_bot)

# Features

- API.
- Telegram bot that uses the API.
- Seeing the song queue through the API and the bot.
- Users.
- Song history.
- Skipping songs.
- Anonymous addition of songs.
- Playlist setup for automated addition of music.
- Webpage for player with *beautiful* design.

# Usage

For convenience, I've created a Dockerfile. To use the application, simply do the following:

```bash
chmod +x build_and_run_docker.sh
bash build_and_run_docker.sh
```

# Ports

The application uses two ports:

- One port is for the frontend, by default it is `12345`. You can change the port for the frontend in the `env` file.
- One port is for the vlc server, by default it is `12346`. You can change the port for the vlc in the `env` file.

# Env file

Sample env file is provided in the repository. Change it for your bot and server location.
