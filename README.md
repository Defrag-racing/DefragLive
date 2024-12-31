# DFTwitchBot

An interface between Twitch chat and DeFRaG.

## Todo List

- [x] Added announcer sounds with commands
- [x] Check if commands such as (called a vote) are from players or server. (Finished, but not guaranteed )
- [ ] On connect, PM each nospec player a reminder that they have nospec on. Use /tell client id msg
- [x] Refactor bot.py to remove the 'elif' galore
- [ ] Integrate forever-free API for ?stonks. Yahoo api is good but only 500 /mo hits free. Look at coingecko for crypto

## Usage

* Step 1: Retrieve a tmi token and client id from the twitch developer portal, paste these into their respective fields
in env.py
* Step 2: Copy the provided .cfg files to your `/defrag/` folder & Copy the music into your `/defrag/` folder.
* Step 3: Change the field "DF_DIR" in env.py to the full path to your `/defrag/` folder
* Step 4: Change the field "DF_EXE_PATH" in env.py to the name of your defrag engine executable
* step 5: Change the field "CHANNEL" in env.py to the name of twitch channel you wish to connect the bot to
* Step 6: Run `python bot.py`
* Step 7: Launch iDFe.exe, or let the bot run it for you. execute the twitch configs
