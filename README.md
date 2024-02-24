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
docker build -t pmb:server .
docker run -p 45554:45554 -p 45555:45555 -d pmb:server
```

# Ports

The application uses two ports:

- `45554` for the frontend. You can change the port for the frontend in the `env` file.
- `45555` for the vlc server. You can change the port for the vlc in the `env` file.

# Env file

Sample env file is provided in the repository. Change it for your bot and server location.
