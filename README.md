# DefragLive Twitch Bot

An interface between Twitch and DeFRaG.

Includes features such as:

- Twitch chat relaying, commands, and an extension ([demonstration](https://youtu.be/ZEHH-3SzFMs))
- AFK player detection
- In-game players are able to opt-out of being spectated (TODO: how)
- In-game chat and server events integration
- Naughty word censoring from players' names and chat

## Quick start

### Installation

Windows:

_TODO_

Linux:

```sh
# Clone this repository
git clone https://github.com/defrag-racing/defraglive.git

# Move into src
cd defraglive/src/

# Create a Python Virtual ENVironment
python3 -m venv .venv

# Activate the venv
. .venv/bin/activate

# Install dependencies in the venv
pip3 -r requirements.txt

# Create env.py
cp env-template.py env.py
```

### Usage

* Step 1:

Retrieve a tmi token and client id from the Twitch developer portal.
Paste them into their respective fields in `env.py`.

* Step 2:

Copy the provided .cfg files to your `/defrag/` folder.
Copy the sound files into your `/defrag/` folder.

* Step 3:

Change the field `"DF_DIR"` in `env.py` to the full path to your `/defrag/` folder

* Step 4:

Change the field `"DF_EXE_PATH"` in `env.py` to your DeFRaG engine executable

* step 5:

Change the field `"CHANNEL"` in `env.py` to your Twitch channel.

* Step 6:

Run `python3 bot.py` (May require a virtual environment from Installation)

* Step 7:

Launch your DeFRaG engine or let the bot run it for you.

* Step 8:

Execute the Twitch configs

## TODO List

- [x] Added announcer sounds with commands
- [x] Check if commands such as (called a vote) are from players or server. (Finished, but not guaranteed )
- [ ] On connect, PM each nospec player a reminder that they have nospec on. Use /tell client id msg
- [x] Refactor bot.py to remove the 'elif' galore
- [ ] Integrate forever-free API for ?stonks. Yahoo api is good but only 500 /mo hits free. Look at coingecko for crypto
- [ ] [Linux support](https://github.com/Defrag-racing/DefragLive/issues/58)
