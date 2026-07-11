'''Copy this file into env.py in the src directory and fill out. DO NOT push changes in this file.'''

environ = {
    "TMI_TOKEN": "",
    "CLIENT_ID": "",
    "BOT_NICK": "",
    "BOT_PREFIX": "?",
    "CFG_NAME": "twitchbot.cfg",
    "DF_DIR": "",
    "DF_EXE_PATH": "",
    "SVINFO_REPORT_NAME": "serverstate.txt",
    "CHANNEL": "",
    "WS_ADDRESS": "ws://localhost:5005",  # legacy bridge WS (unused by web_transport)
    # Web-native transport (replaces the bridge). The bot POSTs to the web API
    # and subscribes to its Reverb channel for commands.
    "WEB_BASE_URL": "https://defrag.racing",
    "WEB_INGEST_TOKEN": "",          # must match DEFRAGLIVE_INGEST_TOKEN on the web
    "REVERB_APP_KEY": "",            # web's REVERB_APP_KEY
    "REVERB_HOST": "tw.defrag.racing",
    "REVERB_PORT": 443,
    "REVERB_SCHEME": "https",
    "FLASK_SERVER": {
        "host": "127.0.0.1",
        "port": 5000
    },
    "LOG_DIR_PATH": "C:\\Absolute\\Path\\To\\Logs\\Folder",
    "TWITCH_API": {
        "client_id": "",
        "client_secret": ""
    },
    "STONK_API": {
        'key': "",
        'host': ""
    },
    "DEVELOPMENT": False, # True if you're developing, False if you're using the production server
    "MAP_DATA": {
        "STORAGE_PATH": "",
        "MAPDATA_TABLE": ""
    }
}
