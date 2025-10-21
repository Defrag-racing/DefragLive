"""
This file contains two important classes that contain the current live state of the game:
State - stores information about the current server, such meta data and players. It contains a set of methods to
         conveniently query information that is expected to be needed frequently.
Player - stores individual in-depth information about each player. The server object's players attribute contains a
         list of these objects

It also contains many important methods that handle different parts of the server state process. See their documentation
for details.
"""

import api
import re
import time
import random
import config
import os
import servers
import logging
import json
import requests
from hashlib import md5
from env import environ
# import mapdata
from websocket_console import notify_serverstate_change
import traceback
import threading
import time


# Configurable variables, Strike = 2seconds
MESSAGE_REPEATS = 1  # How many times to spam info messages. 0 for no messages.
AFK_TIMEOUT = 1000 if config.DEVELOPMENT else 30  # Switch after afk detected x consecutive times.
#AFK_TIMEOUT = 5 if config.DEVELOPMENT else 5  # Switch after afk detected x consecutive times.
IDLE_TIMEOUT = 5 if config.DEVELOPMENT else 5  # Alone in server timeout.
INIT_TIMEOUT = 10  # Determines how many times to try the state initialization before giving up.
STANDBY_TIME = 1 if config.DEVELOPMENT else 15  # Time to wait before switching to next player.
VOTE_TALLY_TIME = 10  # Amount of time to wait while tallying votes
LAST_TEAM_CHECK_TIME = 0
TEAM_CHECK_INTERVAL = 30  # Check every 30 seconds
AFK_COUNTDOWN_ACTIVE = False
AFK_HELP_THREADS = []  # Track active help threads
LAST_GREETING_SERVER = None  # Track which server we last sent greeting to
CONNECTION_START_TIME = None
MAX_CONNECTION_TIMEOUT = 90  # 90 seconds max for any connection attempt
FORCE_RECOVERY_TIMEOUT = 90  # 90 seconds absolute maximum before force recovery
RECOVERY_IN_PROGRESS = False
RECOVERY_ATTEMPTS = 0
MAX_RECOVERY_ATTEMPTS = 3
LAST_RECOVERY_TIME = 0
RECOVERY_COOLDOWN = 15  # 15 seconds between recovery attempts
RECOVERY_TIMEOUT_ACTIVE = False  # Prevent multiple timeout threads

# State paused logging throttle
STATE_PAUSED_COUNTER = 0
LAST_PAUSE_LOG_TIME = 0
PAUSE_LOG_INTERVAL = 10  # Log every 10 pauses or every 30 seconds

# Track failed follow attempts to prevent infinite retry loops
FAILED_FOLLOW_ATTEMPTS = {}  # {player_id: {'timestamp': time, 'count': int}} - track failed attempts
FAILED_FOLLOW_COOLDOWN = 10  # Retry after 10 seconds
MAX_FOLLOW_FAILURES = 3  # Give up after 3 consecutive failures
PERMANENTLY_EXCLUDED = set()  # Player IDs that failed too many times

# Auto greeting messages with Twitch viewer count integration
GREETING_MESSAGES = [
    "^2Hello ^7there! ^3Us ^2{count} ^7arrived to watch you play ^3defrag^7! ^1:)",
    "^3Hi ^7everyone! ^2{count} ^7viewers just joined to see some ^3sick runs^7! ^2:)",
    "^5Greetings ^7fraggers! ^3{count} ^7people are now watching your ^2amazing skills^7!",
    "^4Hey ^7there! ^2{count} ^7viewers just tuned in to watch some ^3defrag action^7! ^1:)",
    "^1Welcome ^7warriors! ^2{count} ^7defrag fans just dropped in to watch the ^3magic happen^7! ^5:)",
    "^4Ayy ^7there! ^3{count} ^7viewers just connected to witness some ^2legendary movement^7!",
    "^6Bonjour ^7speed demons! ^2{count} ^7people are here for the ^3ultimate defrag experience^7! ^1:)",
    "^2Greetings ^7and salutations! ^3{count} ^7viewers joined the ^2defrag party^7! ^4Let's gooo!",
    "^5What's crackin' ^7legends! ^2{count} ^7people tuned in for some ^3insane trick jumps^7!",
    "^1Hola ^7amigos! ^3{count} ^7viewers are ready to see you ^2demolish these records^7! ^6:P",
    "^4Wassup ^7chat! ^2{count} ^7defrag enthusiasts just arrived for the ^3show of shows^7!",
    "^3Konnichiwa ^7runners! ^2{count} ^7viewers joined to watch some ^1sick strafe action^7! ^5:)",
    "^6Ahoy ^7there! ^3{count} ^7people sailed in to see you ^2navigate these maps perfectly^7!",
    "^2Namaste ^7fraggers! ^1{count} ^7souls gathered to witness your ^3transcendent movement^7!",
    "^5Howdy ^7partners! ^3{count} ^7viewers just rode into town for some ^2wild defrag action^7! ^4:)",
    "^1Guten Tag ^7speedsters! ^2{count} ^7viewers arrived to see some ^3precision platforming^7!",
    "^4Shalom ^7legends! ^3{count} ^7people are here to watch you ^2break the laws of physics^7! ^6:)",
    "^2Zdravstvuyte ^7comrades! ^1{count} ^7viewers joined for some ^3communist strafe jumping^7! ^5:P",
    "^6Ni hao ^7masters! ^3{count} ^7viewers came to learn from your ^2ancient defrag wisdom^7!",
    "^5Sup ^7kings and queens! ^2{count} ^7royal subjects arrived to watch your ^3majestic runs^7! ^1:)",
    "^4Yo ^7yo ^7yo! ^3{count} ^7hype beasts just rolled up for the ^2sickest movement tech^7! ^6:)",
    "^1Heeeey ^7there! ^2{count} ^7awesome humans joined to see you ^3absolutely destroy these maps^7!",
    "^3What's good ^7gamers! ^1{count} ^7viewers are locked and loaded for some ^2epic defrag moments^7!",
    "^6Greetings ^7earthlings! ^3{count} ^7beings from across the galaxy came to see you ^2defy gravity^7! ^4:P",
    "^2Salve ^7gladiators! ^1{count} ^7spectators entered the arena to watch you ^3conquer these challenges^7!",
    "^5Hello ^7hello ^7hello! ^3{count} ^7beautiful people joined the ^2defrag family reunion^7! ^6:)",
    "^4Top of the morning! ^2{count} ^7early birds flew in to catch the ^3defrag worm^7! ^1:)",
    "^1Buongiorno ^7artists! ^3{count} ^7viewers came to admire your ^2movement masterpieces^7! ^5:)",
    "^6What's shakin' ^7bacon! ^2{count} ^7hungry viewers arrived for some ^3tasty trick jumps^7! ^4:P",
    "^3Rise and grind ^7champions! ^1{count} ^7motivated viewers joined your ^2training montage^7! ^6:)",
    "^5Peek-a-boo! ^7^2{count} ^7sneaky viewers just appeared to watch you ^3vanish through these maps^7! ^1:)",
    "^4Yooooo ^7what's poppin'! ^3{count} ^7cool cats slid in to see some ^2smooth operator moves^7! ^6:P",
    "^2Beep beep! ^7^1{count} ^7speed demons just drove by to see you ^3burn rubber on these maps^7! ^5:)",
    "^6Ready, set, GO! ^3{count} ^7racers joined the starting line to watch you ^2break land speed records^7! ^4:)",
    "^6What's up ^7gamers! ^3{count} ^7people arrived to see you ^2dominate ^7these maps!",
    "^1Yo ^7yo ^7yo! ^2{count} ^7viewers just showed up for the ^3defrag show^7! ^4:P",
    "^3Sup ^7legends! ^2{count} ^7people are here to witness your ^3epic runs^7!",
    "^5Hello ^7hello! ^3{count} ^7viewers joined the party to watch some ^2quality defrag^7!",
    "^4Howdy ^7there! ^2{count} ^7people just arrived to see you ^3shred ^7these maps! ^1:)",
    "^6G'day ^7mate! ^3{count} ^7viewers are here to watch some ^2sick movement^7!",
    "^2Hiya ^7everyone! ^3{count} ^7people joined to see you ^2crush ^7those times!",
    "^1What's good ^7fam! ^2{count} ^7viewers are ready for some ^3insane defrag action^7!",
    "^4Salutations ^7runners! ^3{count} ^7people are here to watch you ^2fly ^7through these maps!",
    "^5Hey ^7hey ^7hey! ^2{count} ^7viewers just dropped in to see some ^3mad skills^7! ^4:)",
    "^6Aloha ^7fraggers! ^3{count} ^7people are here to witness your ^2legendary runs^7!"
]

# Nationality-specific greetings
NATIONALITY_GREETINGS = {
    'DE': [
        "^2Guten Tag ^7everyone! ^3{count} ^7viewers joined to see some ^2German engineering ^7in defrag! ^1:)",
        "^4Hallo ^7fraggers! ^2{count} ^7people are here to witness some ^3Deutsch precision^7!",
        "^5Servus ^7speed demons! ^3{count} ^7viewers came for the ^2legendary German efficiency^7! ^4:P"
    ],
    'RU': [
        "^1Privet ^7comrades! ^2{count} ^7viewers arrived for some ^3Russian strafe mastery^7! ^5:)",
        "^3Zdravstvuyte ^7legends! ^1{count} ^7people joined to see ^2Eastern European excellence^7!",
        "^6Da da da! ^7^3{count} ^7viewers are here for some ^4Soviet-level movement^7! ^2:P"
    ],
    'FR': [
        "^5Bonjour ^7mes amis! ^2{count} ^7viewers joined for some ^3French finesse^7! ^4:)",
        "^1Salut ^7fraggers! ^3{count} ^7people are here to see ^2Gallic grace ^7in motion!",
        "^4Bonsoir ^7speed artists! ^2{count} ^7viewers came for ^6French flair^7! ^3:P"
    ],
    'US': [
        "^1Howdy ^7y'all! ^3{count} ^7viewers just rolled up for some ^2American awesomeness^7! ^4:)",
        "^2What's up ^7USA! ^1{count} ^7people joined for some ^3Stars and Stripes strafing^7!",
        "^6Hey there ^7Americans! ^2{count} ^7viewers are here for that ^4freedom movement^7! ^5:P"
    ],
    'PL': [
        "^4Cześć ^7Polish legends! ^2{count} ^7viewers joined for some ^3Slavic supremacy^7! ^1:)",
        "^6Witajcie ^7speed demons! ^3{count} ^7people are here for ^2Polish power^7!",
        "^1Siema ^7fraggers! ^2{count} ^7viewers came to witness ^5Polish perfection^7! ^4:P"
    ],
    'SE': [
        "^3Hej ^7Swedish vikings! ^2{count} ^7viewers sailed in for ^1Nordic navigation^7! ^5:)",
        "^6Tjena ^7Scandinavian speedsters! ^3{count} ^7people joined for ^4Swedish smoothness^7!",
        "^2Hallå ^7ice kings! ^1{count} ^7viewers are here for ^6Nordic excellence^7! ^4:P"
    ],
    'GB': [
        "^5Cheerio ^7British legends! ^2{count} ^7viewers joined for some ^3proper English movement^7! ^1:)",
        "^4Blimey ^7UK fraggers! ^3{count} ^7people are here for ^6British brilliance^7!",
        "^1Oi oi ^7speed merchants! ^2{count} ^7viewers came for ^4Queen's English strafing^7! ^5:P"
    ],
    'NL': [
        "^6Hallo ^7Dutch masters! ^3{count} ^7viewers joined for some ^2Netherlands navigation^7! ^4:)",
        "^2Gezellig ^7Orange army! ^1{count} ^7people are here for ^5Dutch dynamics^7!",
        "^4Goedendag ^7fraggers! ^2{count} ^7viewers came for ^3Holland highlights^7! ^6:P"
    ],
    'FI': [
        "^1Hei ^7Finnish fighters! ^3{count} ^7viewers joined for some ^2Nordic navigation^7! ^5:)",
        "^5Terve ^7Suomi speedsters! ^2{count} ^7people came for ^4Finnish finesse^7!",
        "^3Moi ^7ice warriors! ^1{count} ^7viewers are here for ^6Arctic excellence^7! ^4:P"
    ],
    'NO': [
        "^4Hei ^7Norwegian vikings! ^2{count} ^7viewers sailed in for ^3fjord-level movement^7! ^1:)",
        "^6Takk ^7Nordic legends! ^3{count} ^7people joined for ^5Norwegian navigation^7!",
        "^2Hyggelig ^7speed demons! ^1{count} ^7viewers are here for ^4Viking velocity^7! ^5:P"
    ]
}

# Keep last spectate snapshot to avoid spamming identical logs every serverstate change
LAST_SPECTATE_SNAPSHOT = None
LAST_AFK_SNAPSHOT = None
LAST_SWITCH_SNAPSHOT = None
LAST_TEAM_SNAPSHOT = None

def _normalize_ids(id_list):
    """Normalize a list of ids into a sorted tuple of ints for stable snapshots."""
    try:
        return tuple(sorted(int(x) for x in id_list)) if id_list else ()
    except Exception:
        # Fallback: convert to string-sorted tuple
        return tuple(sorted(str(x) for x in id_list)) if id_list else ()

def get_dominant_nationality(server_data):
    """
    Analyze server data to find the most common nationality
    Returns the country code of the dominant nationality, or None if no clear winner
    """
    if 'players' not in server_data or not server_data['players']:
        return None
    
    country_counts = {}
    total_players = 0
    
    # Count countries (excluding the bot)
    for player_id, player_data in server_data['players'].items():
        if isinstance(player_data, dict) and 'country' in player_data:
            # Skip the bot (DefragLive)
            player_name = player_data.get('name', '').lower()
            if 'defrag.live' in player_name or 'defraglive' in player_name:
                continue
                
            country = player_data['country']
            country_counts[country] = country_counts.get(country, 0) + 1
            total_players += 1
    
    if total_players == 0:
        return None
    
    # Find the most common country
    dominant_country = max(country_counts, key=country_counts.get)
    dominant_count = country_counts[dominant_country]
    
    # Only return if it represents at least 50% of players (or at least 2 players)
    if dominant_count >= max(2, total_players * 0.5):
        return dominant_country
    
    return None

def send_nationality_greeting(server_ip):
    logging.info(f"[GREETING DEBUG] send_nationality_greeting called with IP: {server_ip}")
    """
    Send a nationality-specific greeting based on server composition
    """
    try:
        # Fetch server data
        import requests
        url = 'https://defrag.racing/servers/json'
        response = requests.get(url, timeout=5)
        servers_data = response.json()
        
        # Add default port if not present
        api_ip = server_ip if ':' in server_ip else f"{server_ip}:27960"
        
        if 'active' not in servers_data or api_ip not in servers_data['active']:
            # Fallback to regular greeting
            send_auto_greeting()
            return
        
        server_data = servers_data['active'][api_ip]
        dominant_country = get_dominant_nationality(server_data)
        
        if dominant_country and dominant_country in NATIONALITY_GREETINGS:
            # Use nationality-specific greeting
            viewer_count = get_twitch_viewer_count()
            if viewer_count < 1:
                viewer_count = random.randint(1, 5)
            
            greeting_template = random.choice(NATIONALITY_GREETINGS[dominant_country])
            greeting_message = greeting_template.format(count=viewer_count)
            
            logging.info(f"Sending nationality greeting for {dominant_country}: {greeting_message}")
            api.exec_command(f"say {greeting_message}")
        else:
            # Fallback to regular greeting
            send_auto_greeting()
            
    except Exception as e:
        logging.error(f"Error sending nationality greeting: {e}")
        # Fallback to regular greeting
        send_auto_greeting()

# World record celebration messages
WORLD_RECORD_MESSAGES = [
    "^1HOLY MOLY! ^7We just witnessed ^3HISTORY ^7being made! ^2What a legendary run! ^5:))",
    "^2INCREDIBLE! ^7That was absolutely ^3PHENOMENAL^7! ^1World record SMASHED! ^4:)",
    "^3WOW WOW WOW! ^7^2{count} ^7viewers just saw something ^1EXTRAORDINARY^7! ^6AMAZING!",
    "^4UNBELIEVABLE! ^7That was ^3PURE MAGIC^7! ^2History books will remember this moment! ^5:P",
    "^5MIND = BLOWN! ^7We are ^3BLESSED ^7to witness such ^2INCREDIBLE skill^7! ^1:))",
    "^6SPEECHLESS! ^7That run was ^3ABSOLUTELY PERFECT^7! ^4World record DESTROYED! ^2:)",
    "^1GOOSEBUMPS! ^7What a ^3MASTERPIECE ^7of movement! ^5Truly witnessing greatness! ^6:))",
    "^2LEGENDARY! ^7That was ^3POETRY IN MOTION^7! ^1The stars aligned for this run! ^4:P",
    "^3CHILLS EVERYWHERE! ^7We just saw the ^2IMPOSSIBLE ^7become possible! ^5EPIC! ^1:)",
    "^4HISTORY MADE! ^7That run will be talked about for ^3YEARS TO COME^7! ^6BRILLIANT! ^2:))",
    "^5PERFECTION! ^7Every single movement was ^3FLAWLESS^7! ^1Absolutely STUNNING! ^4:)",
    "^6WORLD CLASS! ^7That wasn't just a run, that was ^3ART^7! ^2PHENOMENAL performance! ^5:P",
    "^1MAGICAL! ^7The universe conspired to create this ^3PERFECT MOMENT^7! ^6AMAZING! ^4:))",
    "^2TRANSCENDENT! ^7We witnessed something ^3BEYOND HUMAN^7! ^5Absolutely MAGNIFICENT! ^1:)",
    "^3SUBLIME! ^7That run had everything - ^2skill, precision, and HEART^7! ^4INCREDIBLE! ^6:P",
    "^1INSANE! ^7That movement was ^3OUT OF THIS WORLD^7! ^2Absolutely MINDBLOWING! ^5:D",
    "^2EPIC WIN! ^7We just witnessed ^3DEFRAG PERFECTION^7! ^4LEGENDARY status achieved! ^6:P",
    "^3BONKERS! ^7That was ^1COMPLETELY MENTAL^7! ^5The physics gods smiled today! ^2:))",
    "^4GODLIKE! ^7Movement like that is ^3ONCE IN A LIFETIME^7! ^6SPECTACULAR! ^1:D",
    "^5UNTOUCHABLE! ^7That run was ^2ABSOLUTE PERFECTION^7! ^3Nobody else even comes close! ^4:)",
    "^6FLAWLESS VICTORY! ^7Every single pixel was ^1PERFECTLY CALCULATED^7! ^2GENIUS! ^5:P",
    "^1NEXT LEVEL! ^7That wasn't just fast, that was ^3TRANSCENDENT^7! ^4UNREAL! ^6:))",
    "^2PURE EXCELLENCE! ^7Movement so smooth it looked ^3EFFORTLESS^7! ^5MASTERFUL! ^1:D",
    "^3MIND-MELTING! ^7We just saw the ^4IMPOSSIBLE^7 become reality! ^6EXTRAORDINARY! ^2:P",
    "^4BREATHTAKING! ^7That run left everyone ^1ABSOLUTELY STUNNED^7! ^3PHENOMENAL! ^5:)",
    "^5GAME CHANGER! ^7Movement like that ^2REDEFINES THE POSSIBLE^7! ^6INCREDIBLE! ^1:D",
    "^6OTHERWORLDLY! ^7That wasn't human, that was ^3PURE ARTISTRY^7! ^4MAGNIFICENT! ^2:))",
    "^1DEMOLITION! ^7The previous record got ^5COMPLETELY OBLITERATED^7! ^3SAVAGE! ^6:P",
    "^2UNSTOPPABLE! ^7Movement so clean it looked ^4COMPUTER-GENERATED^7! ^1PERFECT! ^5:D",
    "^3LEGENDARY STATUS! ^7That run will be remembered ^2FOREVER^7! ^6HISTORIC! ^4:)",
    "^4REALITY BENDING! ^7Physics laws were ^1COMPLETELY IGNORED^7! ^3SUPERNATURAL! ^2:P",
    "^5MASTERPIECE! ^7Every strafe was ^6PIXEL-PERFECT^7! ^4ARTISTIC BRILLIANCE! ^1:D",
    "^6GODMODE ACTIVATED! ^7That movement was ^3ABSOLUTELY DIVINE^7! ^5CELESTIAL! ^2:))",
    "^1NUCLEAR! ^7That run just ^4EXPLODED^7 the leaderboards! ^3DEVASTATING! ^6:P",
    "^2UNTAMED! ^7Raw skill like that is ^5COMPLETELY WILD^7! ^1FEROCIOUS! ^4:D",
    "^3SILKY SMOOTH! ^7Movement so fluid it was ^6HYPNOTIC^7! ^2MESMERIZING! ^5:)",
    "^4STRATOSPHERIC! ^7That performance was ^1SKY-HIGH^7 quality! ^3ASTRONOMICAL! ^6:P",
    "^5FLAWLESS EXECUTION! ^7Not a single wasted movement! ^2CLINICAL PRECISION! ^4:D",
    "^6MIND-BOGGLING! ^7Speed and accuracy beyond ^3HUMAN COMPREHENSION^7! ^1SURREAL! ^5:)",
    "^1RECORD ANNIHILATION! ^7The old time got ^4COMPLETELY VAPORIZED^7! ^6RUTHLESS! ^2:P",
    "^2PURE VELOCITY! ^7Movement so fast it ^5BROKE THE SOUND BARRIER^7! ^3SONIC! ^4:D",
    "^3SURGICAL PRECISION! ^7Every angle calculated to ^1MATHEMATICAL PERFECTION^7! ^6GENIUS! ^5:)",
    "^4LIGHTNING STRIKE! ^7That run hit with ^2ELECTRIFYING SPEED^7! ^3THUNDEROUS! ^1:P",
    "^5DEFRAG DEITY! ^7Movement blessed by the ^6STRAFE JUMPING GODS^7! ^4DIVINE! ^2:D",
    "^6REALITY CHECK! ^7What we just saw ^1SHOULDN'T BE POSSIBLE^7! ^5MIRACULOUS! ^3:)",
    "^1ABSOLUTE MADNESS! ^7That level of skill is ^4COMPLETELY INSANE^7! ^2BONKERS! ^6:P",
    "^2MOVEMENT POETRY! ^7Every strafe told a ^3BEAUTIFUL STORY^7! ^5ARTISTIC! ^1:D",
    "^3SPEED DEMON! ^7That runner just ^6POSSESSED^7 the map! ^4SUPERNATURAL! ^2:)",
    "^4PERFECTION ACHIEVED! ^7The ^1ULTIMATE RUN^7 has been witnessed! ^5FLAWLESS! ^3:P",
    "^5LEGENDARY BEAST! ^7Movement so wild it ^2TAMED THE IMPOSSIBLE^7! ^6UNTAMED! ^4:D",
    "^6QUANTUM LEAP! ^7That run just ^3TELEPORTED^7 into the history books! ^1FUTURISTIC! ^5:)"
]

# Rate limiting for world records
LAST_WR_MESSAGE_TIME = 0
WR_MESSAGE_COOLDOWN = 60  # 1 minute

# Twitch account validation cache
TWITCH_ACCOUNT_CACHE = {}  # username -> (exists, timestamp)
TWITCH_LIVE_CACHE = {}  # username -> (is_live, timestamp)
TWITCH_CACHE_EXPIRY = 300  # 5 minutes cache expiry
TWITCH_LIVE_CACHE_EXPIRY = 60  # 1 minute cache for live status (more frequent updates needed)
TWITCH_ERROR_BACKOFF = {}  # username -> (last_error_time, consecutive_errors)

RECONNECTED_CHECK = False

CURRENT_IP = None

STATE = None
PAUSE_STATE = False
IGNORE_IPS = []
CONNECTING = False
VID_RESTARTING = False
STATE_INITIALIZED = False
LAST_REPORT_TIME = time.time()
LAST_INIT_REPORT_TIME = time.time()

# mapdata_thread = threading.Thread(target=mapdata.mapdataHook, daemon=True)

def save_serverstate_to_file():
    try:
        if STATE and hasattr(STATE, 'players'):
            import websocket_console
            import json
            import os
            
            # Use storage directory for runtime data
            storage_dir = os.path.join(os.path.dirname(__file__), '..', 'storage')
            os.makedirs(storage_dir, exist_ok=True)
            filepath = os.path.join(storage_dir, 'serverstate.json')
            
            data = websocket_console.serverstate_to_json()
            with open(filepath, 'w') as f:
                json.dump(data, f)
    except Exception as e:
        logging.error(f"Failed to save serverstate: {e}")

def get_twitch_viewer_count():
    """
    Get current Twitch viewer count for defraglive channel
    Returns viewer count as integer, or 0 if error occurs
    """
    try:
        client_id = environ['TWITCH_API']['client_id']
        client_secret = environ['TWITCH_API']['client_secret']
        token_url = "https://id.twitch.tv/oauth2/token"
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
        token_response = requests.post(token_url, data=token_data, timeout=10)
        token_response.raise_for_status()
        token = token_response.json()['access_token']
        stream_url = f"https://api.twitch.tv/helix/streams?user_login={'defraglive'}"
        headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
        response = requests.get(stream_url, headers=headers, timeout=10)
        response.raise_for_status()
        stream_data = response.json()['data']
        return stream_data[0]['viewer_count'] if stream_data else 0
    except Exception as e:
        logging.error(f"Error getting Twitch viewer count: {e}")
        return 0

def check_twitch_account_exists(username):
    """
    Check if a Twitch account exists with caching to avoid excessive API calls
    Returns True if account exists, False if not found or error occurs
    """
    global TWITCH_ACCOUNT_CACHE
    current_time = time.time()

    # Check cache first
    if username in TWITCH_ACCOUNT_CACHE:
        exists, timestamp = TWITCH_ACCOUNT_CACHE[username]
        if current_time - timestamp < TWITCH_CACHE_EXPIRY:
            return exists

    try:
        client_id = environ['TWITCH_API']['client_id']
        client_secret = environ['TWITCH_API']['client_secret']
        token_url = "https://id.twitch.tv/oauth2/token"
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
        token_response = requests.post(token_url, data=token_data, timeout=10)
        token_response.raise_for_status()
        token = token_response.json()['access_token']
        user_url = f"https://api.twitch.tv/helix/users?login={username}"
        headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
        response = requests.get(user_url, headers=headers, timeout=10)
        response.raise_for_status()
        user_data = response.json()['data']
        exists = len(user_data) > 0  # Account exists if user data returned

        # Cache the result
        TWITCH_ACCOUNT_CACHE[username] = (exists, current_time)

        return exists
    except Exception as e:
        logging.error(f"Error checking Twitch account existence {username}: {e}")
        # Cache negative result for failed API calls to avoid spam
        TWITCH_ACCOUNT_CACHE[username] = (False, current_time)
        return False

def check_twitch_channel_live(username):
    """
    Check if a Twitch channel is currently live with caching and error backoff
    Returns True if live, False if not live or error occurs
    """
    global TWITCH_LIVE_CACHE, TWITCH_ERROR_BACKOFF
    current_time = time.time()

    # Check if we should skip due to recent errors (exponential backoff)
    if username in TWITCH_ERROR_BACKOFF:
        last_error_time, consecutive_errors = TWITCH_ERROR_BACKOFF[username]
        backoff_time = min(300, 30 * (2 ** consecutive_errors))  # Max 5 minutes backoff
        if current_time - last_error_time < backoff_time:
            logging.debug(f"Skipping Twitch check for {username} due to backoff ({backoff_time}s)")
            return False

    # Check cache first
    if username in TWITCH_LIVE_CACHE:
        is_live, timestamp = TWITCH_LIVE_CACHE[username]
        if current_time - timestamp < TWITCH_LIVE_CACHE_EXPIRY:
            return is_live

    try:
        client_id = environ['TWITCH_API']['client_id']
        client_secret = environ['TWITCH_API']['client_secret']
        token_url = "https://id.twitch.tv/oauth2/token"
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
        token_response = requests.post(token_url, data=token_data, timeout=10)
        token_response.raise_for_status()
        token = token_response.json()['access_token']

        stream_url = f"https://api.twitch.tv/helix/streams?user_login={username}"
        headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
        response = requests.get(stream_url, headers=headers, timeout=10)
        response.raise_for_status()
        stream_data = response.json()['data']
        is_live = len(stream_data) > 0  # Live if stream data exists

        # Cache the successful result
        TWITCH_LIVE_CACHE[username] = (is_live, current_time)

        # Clear error backoff on success
        if username in TWITCH_ERROR_BACKOFF:
            del TWITCH_ERROR_BACKOFF[username]

        return is_live
    except Exception as e:
        logging.error(f"Error checking Twitch channel {username}: {e}")

        # Update error backoff
        if username in TWITCH_ERROR_BACKOFF:
            last_error_time, consecutive_errors = TWITCH_ERROR_BACKOFF[username]
            TWITCH_ERROR_BACKOFF[username] = (current_time, consecutive_errors + 1)
        else:
            TWITCH_ERROR_BACKOFF[username] = (current_time, 1)

        # Cache negative result for failed API calls to avoid spam
        TWITCH_LIVE_CACHE[username] = (False, current_time)
        return False


def send_auto_greeting():
    logging.info(f"[GREETING DEBUG] send_auto_greeting called")
    """
    Send an automatic greeting message with current viewer count
    """
    try:
        viewer_count = get_twitch_viewer_count()
        
        # Don't send greeting if no viewers or very low count (to avoid spam when testing)
        if viewer_count < 1:
            viewer_count = random.randint(1, 5)  # Fallback for offline testing
        
        # Select random greeting message
        greeting_template = random.choice(GREETING_MESSAGES)
        greeting_message = greeting_template.format(count=viewer_count)
        
        logging.info(f"Sending auto greeting: {greeting_message}")
        api.exec_command(f"say {greeting_message}")
        
    except Exception as e:
        logging.error(f"Error sending auto greeting: {e}")


class State:
    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

    """
    Class that stores data about the state of the server and players
    """

    def __init__(self, secret, server_info, players, bot_id):
        for key in server_info:
            setattr(self, key.replace('sv_', ''), server_info[key])
        self.players = players
        self.secret = secret
        self.bot_id = bot_id
        self.current_player = None
        self.current_player_id = -1
        self.idle_counter = 0
        self.afk_counter = 0
        if self.bot_id in self.spec_ids:
            self.spec_ids.remove(self.bot_id)
        self.afk_ids = []
        self.afk_timestamps = {}  # Track when each player was flagged as AFK (player_id -> timestamp)
        self.connect_msg = None
        self.vote_time = time.time()
        self.vy_count = 0
        self.vn_count = 0
        self.voter_names = []
        self.show_name = True
        # NEW: Track custom AFK timeouts per player
        self.player_afk_timeouts = {}  # player_id -> custom_timeout

    def get_afk_timeout_for_player(self, player_id):
        """Get the AFK timeout for a specific player, defaulting to global AFK_TIMEOUT"""
        return self.player_afk_timeouts.get(str(player_id), AFK_TIMEOUT)

    def set_afk_timeout_for_player(self, player_id, timeout):
        """Set a custom AFK timeout for a specific player"""
        self.player_afk_timeouts[str(player_id)] = timeout

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def update_info(self, server_info):
        """Helper function for resetting the class's properties on state refresh"""
        for key in server_info:
            setattr(self, key.replace('sv_', ''), server_info[key])
        
        # FIX: Find the actual bot player by the secret code and update bot_id
        bot_player = None
        for player in self.players:
            if player.c1 == self.secret:  # Bot player has the secret as color1
                bot_player = player
                self.bot_id = player.id  # Update bot_id to new server's ID
                break
        
        if bot_player:
            # Verify bot_id is still correct (can change during map changes/server switches)
            new_bot_id = bot_player.id
            if new_bot_id != self.bot_id:
                logging.warning(f"BOT ID MISMATCH DETECTED!")
                logging.warning(f"  Old bot_id: {self.bot_id}")
                logging.warning(f"  New bot_id: {new_bot_id}")
                logging.warning(f"  Current player_id: {self.current_player_id}")
                logging.warning(f"  Updating bot_id to {new_bot_id}")
                self.bot_id = new_bot_id
                # If we were spectating ourselves with wrong ID, reset to new bot_id
                if self.current_player_id == self.bot_id or self.current_player_id not in [p.id for p in self.players]:
                    self.current_player_id = self.bot_id
                    logging.warning(f"  Reset current_player_id to new bot_id: {self.bot_id}")

            # Only reset current_player_id if it's invalid, don't always reset to bot_id
            # Convert player IDs to int for proper comparison
            player_ids = [int(p.id) for p in self.players]
            if self.current_player_id not in player_ids:
                # DEBUG: Add comprehensive logging for player reset
                logging.info(f"RESET DEBUG: Current player ID {self.current_player_id} not found in player list")
                logging.info(f"RESET DEBUG: Available player IDs: {player_ids}")
                logging.info(f"RESET DEBUG: All players: {[(p.id, p.n, p.t, p.c1) for p in self.players]}")
                logging.info(f"RESET DEBUG: Bot ID: {self.bot_id}")

                self.current_player_id = self.bot_id
                logging.info(f"Reset current_player_id to bot_id due to invalid player")
        
        self.current_player = self.get_player_by_id(self.current_player_id)
        if self.bot_id in self.spec_ids:
            self.spec_ids.remove(self.bot_id)
        # remove afk players from speccable id list
        [self.spec_ids.remove(afk_id) for afk_id in self.afk_ids if afk_id in self.spec_ids]

        # Remove permanently excluded players (too many consecutive failures)
        global PERMANENTLY_EXCLUDED
        perm_excluded = [pid for pid in self.spec_ids if pid in PERMANENTLY_EXCLUDED]
        if perm_excluded:
            [self.spec_ids.remove(pid) for pid in perm_excluded]
            logging.info(f"Permanently excluded players (too many failures): {perm_excluded}")

        # Remove players with recent failed follow attempts (cooldown period)
        global FAILED_FOLLOW_ATTEMPTS, FAILED_FOLLOW_COOLDOWN
        current_time = time.time()
        players_to_remove = []
        for player_id, fail_data in list(FAILED_FOLLOW_ATTEMPTS.items()):
            fail_time = fail_data['timestamp']
            # If cooldown has expired, remove from failed list and allow retrying
            if current_time - fail_time > FAILED_FOLLOW_COOLDOWN:
                del FAILED_FOLLOW_ATTEMPTS[player_id]
                logging.info(f"Cooldown expired for player {player_id} - can retry spectating (attempt {fail_data['count'] + 1})")
            # If still in cooldown and player is in spec_ids, remove them temporarily
            elif player_id in self.spec_ids:
                players_to_remove.append(player_id)

        if players_to_remove:
            [self.spec_ids.remove(pid) for pid in players_to_remove]
            logging.info(f"Temporarily excluded players with failed follow attempts: {players_to_remove}")

        # Build a compact snapshot of the spectate-related state and only log when it changes
        try:
            # Normalize player id lists for stable snapshots
            from config import LOG_ONLY_CHANGES

            spec_list = tuple((self.get_player_by_id(pid).n if self.get_player_by_id(pid) else 'Unknown', int(pid)) for pid in _normalize_ids(self.spec_ids))
            nospec_list = tuple((self.get_player_by_id(pid).n if self.get_player_by_id(pid) else 'Unknown', int(pid), self.get_player_by_id(pid).c1 if self.get_player_by_id(pid) else 'Unknown') for pid in _normalize_ids(self.nospec_ids))
            afk_list = tuple((self.get_player_by_id(pid).n if self.get_player_by_id(pid) else 'Unknown', int(pid)) for pid in _normalize_ids(self.afk_ids))
            free_specs = tuple((p.n, int(p.id)) for p in self.players if p.t == '3')
            current_spec = (self.current_player.n if self.current_player else 'None', int(self.current_player_id) if self.current_player_id is not None else None)

            snapshot = (spec_list, nospec_list, afk_list, free_specs, current_spec)
        except Exception:
            snapshot = None

        global LAST_SPECTATE_SNAPSHOT
        # Respect config toggle to allow full-verbose logs when desired
        if not LOG_ONLY_CHANGES or snapshot is None or snapshot != LAST_SPECTATE_SNAPSHOT:
            LAST_SPECTATE_SNAPSHOT = snapshot
            logging.info(f"SPECTATE DEBUG: Spectatable players: {list(spec_list)}")
            logging.info(f"SPECTATE DEBUG: NoSpec players: {list(nospec_list)}")
            logging.info(f"SPECTATE DEBUG: AFK players: {list(afk_list)}")
            logging.info(f"SPECTATE DEBUG: Free spectators (team 3): {list(free_specs)}")
            logging.info(f"SPECTATE DEBUG: Current spectating: {current_spec[0]} (ID: {current_spec[1]})")

    def get_player_by_id(self, c_id):
        """Helper function for easily retrieving a player object from a client id number"""
        id_player = [player for player in self.players if int(player.id) == int(c_id)]
        id_player = id_player[0] if len(id_player) > 0 else None
        return id_player

    def get_first_player(self):
        """Helper function for easily retrieving the first player object that is not a bot"""
        for spec_id in self.spec_ids:
            if spec_id != self.bot_id:
                return spec_id

        return None

    def get_inputs(self):
        """Helper functions for easily retrieving the latest inputs recorded from the watched player."""
        bot_player = self.get_player_by_id(self.bot_id)

        if bot_player is None:
            return 'F'

        return bot_player.c2.replace(' ', '')

    def get_specable_players(self):
        """Helper function to return a list of speccable players as a human-readable string"""
        specable_players = ""
        for spec_id in self.spec_ids:
            plyr = self.get_player_by_id(spec_id)
            plyr_string = f" {plyr.n} (id {spec_id}) |"
            specable_players += plyr_string
        return f'{specable_players.rstrip("|")}'

    def get_nospec_players(self):
        """Helper function to return a list of nospec players as a human-readable string"""
        nospec_players = ""
        for spec_id in self.nospec_ids:
            plyr = self.get_player_by_id(spec_id)
            plyr_string = f" {plyr.n} |"
            nospec_players += plyr_string
        return f'{nospec_players.rstrip("|")}'

    def say_connect_msg(self):
        if self.connect_msg is not None:
            api.exec_command(f"say {self.connect_msg}")
            self.connect_msg = None
        
        # Add nationality-based greeting after custom connect message
        def delayed_nationality_greeting():
            import time
            time.sleep(3)  # 3 second delay
            send_nationality_greeting(self.ip)  # Use the current server IP
        
        greeting_thread = threading.Thread(target=delayed_nationality_greeting, daemon=True)
        greeting_thread.start()

    def init_vote(self):
        self.vote_active = True
        self.vote_time = time.time()
        self.voter_names = []
        self.vy_count = 0
        self.vn_count = 0

    def handle_vote(self):
        if time.time() - self.vote_time > VOTE_TALLY_TIME:
            logging.info("Voting tally done.")
            if self.vn_count > self.vy_count:
                api.exec_command(f"say ^3{self.vy_count} ^2f1 ^7vs. ^3{self.vn_count} ^1f2^7. Voting ^3f2^7.")
                logging.info(f"{self.vy_count} f1s vs. {self.vn_count} f2s. Voting f2.")
                api.exec_command("vote no")
            elif self.vy_count > self.vn_count:
                api.exec_command(f"say ^3{self.vy_count} ^2f1 ^7vs. ^3{self.vn_count} ^1f2^7. Voting ^3f1^7.")
                logging.info(f"{self.vy_count} f1s vs. {self.vn_count} f2s. Voting f1.")
                api.exec_command("vote yes")
            else:
                api.exec_command(f"say ^3{self.vy_count} ^2f1 ^7vs. ^3{self.vn_count} ^1f2^7. No action.")
                logging.info(f"{self.vy_count} f1s vs. {self.vn_count} f2s. Not voting.")

            self.vote_time = 0
            self.voter_names = []
            self.vy_count = 0
            self.vn_count = 0
            self.vote_active = False
        else:
            return


class Player:
    """
    Simple class for storing data about each client/player present in the server.
    """

    def __init__(self, id, player_data):
        self.id = id
        for key in player_data:
            setattr(self, key, player_data[key])
        self.nospec = self.c1 == 'nospec' or self.c1 == 'nospecpm'
        self.nopm = self.c1 == 'nospecpm'


def start():
    """
    The main gateway for fetching the server state through /svinfo_report. It runs through a loop indefinitely and
    attempts to extract new data only if state is not paused through the PAUSE_STATE flag.
    """
    global STATE
    global PAUSE_STATE
    global VID_RESTARTING

    state_paused_timer = 0

    prev_state, prev_state_hash, curr_state = None, None, None
    initialize_state()
    while True:
        try:
            if PAUSE_STATE:
                raise Exception("Paused")
            elif new_report_exists(config.INITIAL_REPORT_P):
                initialize_state()

            # Only refresh the STATE object if new data has been read and if state is not paused
            while not new_report_exists(config.INITIAL_REPORT_P) and not PAUSE_STATE:
                time.sleep(2)

                try:
                    save_serverstate_to_file()
                except Exception as e:
                    logging.error(f"Error saving serverstate to file: {e}")

                if not PAUSE_STATE:
                    api.exec_command("varmath color2 = $chsinfo(152);"  # Store inputs in color2
                                           "silent svinfo_report serverstate.txt", verbose=False)  # Write a new report
                    # Wait 0.5s to ensure file is completely written before reading
                    time.sleep(0.5)
                elif not VID_RESTARTING:
                    raise Exception("VidPaused")

                if new_report_exists(config.STATE_REPORT_P):
                    # Given that a new report exists, read this new data.
                    server_info, players, num_players = get_svinfo_report(config.STATE_REPORT_P)

                    # Validate: if player count drops drastically, likely corrupt read - wait and retry
                    if bool(server_info) and STATE is not None and num_players is not None:
                        if STATE.num_players is not None and STATE.num_players > 5:
                            # If we had many players and suddenly only see half or less, likely corrupt read
                            if num_players < (STATE.num_players * 0.5):  # More than 50% drop
                                logging.warning(f"CORRUPT READ DETECTED: Player count dropped from {STATE.num_players} to {num_players}. Waiting 2s for next report...")
                                time.sleep(2)
                                # Request fresh report and read again
                                api.exec_command("silent svinfo_report serverstate.txt", verbose=False)
                                time.sleep(0.5)
                                server_info, players, num_players = get_svinfo_report(config.STATE_REPORT_P)
                                logging.info(f"Re-read complete: now showing {num_players} players")

                    if STATE is None:
                        # STATE is None, reinitialize
                        logging.warning("STATE is None during update, reinitializing...")
                        if not initialize_state():
                            logging.error("Failed to initialize state, will retry on next update cycle")
                            continue

                    if bool(server_info) and STATE is not None:   # New data is not empty and valid. Update the state object.
                        STATE.players = players
                        STATE.update_info(server_info)
                        STATE.num_players = num_players
                        validate_state()  # Check for nospec, self spec, afk, and any other problems.
                        curr_state_hash = md5(f'{curr_state}_{num_players}_{str([pl.__dict__ for pl in STATE.players])}'.encode('utf-8')).digest()
                        if STATE.current_player is not None and STATE.current_player_id != STATE.bot_id:
                            curr_state = f"Spectating {STATE.current_player.n} on {STATE.mapname}" \
                                         f" in server {STATE.hostname} | ip: {STATE.ip}"
                        if curr_state_hash != prev_state_hash:
                            # Notify all websocket clients about new serverstate
                            notify_serverstate_change()
                        prev_state = curr_state
                        prev_state_hash = curr_state_hash
                        display_player_name(STATE.current_player_id)
                    else:
                        # Data was invalid but STATE exists - just skip this update and try again next cycle
                        logging.warning(f"Skipping serverstate update - server_info empty or invalid (server_info={bool(server_info)}, STATE={STATE is not None})")
                if getattr(STATE, 'vote_active', False) and STATE is not None:
                    STATE.handle_vote()
        except Exception as e:
            if e.args[0] == 'Paused':
                global STATE_PAUSED_COUNTER, LAST_PAUSE_LOG_TIME

                # Increment counter
                STATE_PAUSED_COUNTER += 1
                current_time = time.time()
                time_since_last_log = current_time - LAST_PAUSE_LOG_TIME if LAST_PAUSE_LOG_TIME > 0 else 0

                # Log every 10 pauses, or force a log if 30+ seconds passed (heartbeat)
                is_interval = STATE_PAUSED_COUNTER % PAUSE_LOG_INTERVAL == 0
                is_heartbeat = time_since_last_log >= 30

                if is_interval or is_heartbeat:
                    heartbeat_marker = " [heartbeat]" if is_heartbeat and not is_interval else ""
                    logging.info(f"State paused ({STATE_PAUSED_COUNTER} checks){heartbeat_marker}")
                    LAST_PAUSE_LOG_TIME = current_time

                # state_paused_timer += 1

                # if state_paused_timer > 60:
                #     prev_state, prev_state_hash, curr_state = None, None, None
                #     initialize_state()
                #     state_paused_timer = 0
                #     PAUSE_STATE = False
                # pass
            elif e.args[0] == 'VidPaused':
                logging.info("Vid paused.")
            else:
                prev_state, prev_state_hash, curr_state = None, None, None
                initialize_state()  # Handle the first state fetch. Some extra processing needs to be done this time.
                logging.info(f"State failed: {e}")
                print(traceback.format_exc())
                logging.info(f"State failed: {e}")
            time.sleep(2)


def initialize_state(force=False):
    """
    Handles necessary processing on the first iteration of state retrieval.
    Important steps done here:
        - Check if there's a valid connection
        - Retrieve the bot's client id using the "color1" cvar and a fresh secret code
    """
    global STATE
    global PAUSE_STATE
    global INIT_TIMEOUT
    global STATE_INITIALIZED
    global LAST_TIME
    global AFK_COUNTDOWN_ACTIVE
    global AFK_HELP_THREADS
    global LAST_GREETING_SERVER
    global CURRENT_IP

    # RESET AFK FLAGS ON INITIALIZATION
    AFK_COUNTDOWN_ACTIVE = False
    AFK_HELP_THREADS.clear()

    try:
        # Create a secret code. Only "secret" for one use.
        secret = ''.join(random.choice('0123456789ABCDEF') for i in range(16))
        server_info, bot_player, timeout_flag = None, [], 0

        init_counter = 0
        while server_info is None or bot_player == [] or force == True:  # Continue running this block until valid data and bot id found
            force = False
            init_counter += 1
            if not PAUSE_STATE:
                # Set color1 to secret code to determine bot's client id
                api.exec_command(f"seta color1 {secret};silent svinfo_report serverstate.txt", verbose=False)
            else:
                raise Exception("Paused.")

            if new_report_exists(config.STATE_REPORT_P):  # New data detected
                server_info, players, num_players = get_svinfo_report(config.STATE_REPORT_P)  # Read data
                # Select player that contains this secret as their color1, this will be the bot player.
                bot_player = [player for player in players if player.c1 == secret]

            # If loop hits the max iterations, the connection was not established properly
            if init_counter >= INIT_TIMEOUT:
                # Retry a connection to best server
                new_ip = servers.get_next_active_server(IGNORE_IPS)
                logging.info("[SERVERSTATE] Connecting Now : " + str(new_ip))
                connect(new_ip)

        bot_id = bot_player[0].id  # Find our own ID

        # Create global server object
        STATE = State(secret, server_info, players, bot_id)
        STATE.current_player_id = bot_id
        STATE.current_player = STATE.get_player_by_id(bot_id)  # Ensure current_player is set
        STATE.num_players = num_players
        STATE_INITIALIZED = True
        logging.info("State Initialized.")

        # Force bot to spectator mode to prevent joining as player
        logging.info(f"TEAM DEBUG: Bot current team before 'team s': {STATE.get_player_by_id(bot_id).t if STATE.get_player_by_id(bot_id) else 'Unknown'}")
        api.exec_command("team s")
        logging.info("Bot forced to spectator mode after initialization")
        time.sleep(3)

        # Check if team switch was successful
        # Refresh state to get updated team info
        api.exec_command("svinfo_report serverstate.txt", verbose=False)
        time.sleep(1)
        if new_report_exists(config.STATE_REPORT_P):
            _, updated_players, _ = get_svinfo_report(config.STATE_REPORT_P)
            updated_bot = [player for player in updated_players if player.id == bot_id]
            if updated_bot:
                logging.info(f"TEAM DEBUG: Bot team after 'team s': {updated_bot[0].t}")
                if updated_bot[0].t != '3':
                    logging.warning(f"TEAM DEBUG: 'team s' failed! Bot still on team {updated_bot[0].t}, retrying...")
                    api.exec_command("team s")
                    time.sleep(2)
                else:
                    logging.info("TEAM DEBUG: Bot successfully switched to spectator mode (team 3)")
            else:
                logging.warning("TEAM DEBUG: Could not find bot in updated player list after team switch")

        # Handle nospec notifications
        for nospecid in STATE.nospec_ids:
            if nospecid in STATE.nopmids:
                # Send one-time message to nospecpm players
                api.exec_command('tell ' + str(nospecid) + ' ^7nospec active, ^3defraglive ^7cant spectate.')
                time.sleep(2)
                continue
            api.exec_command('tell ' + str(nospecid) + ' Detected nospec, to disable this feature write /color1 spec')
            time.sleep(2)
            api.exec_command('tell ' + str(nospecid) + ' To disable private notifications about nospec, set /color1 nospecpm')        
    except Exception as e:
        logging.error(f"State initialization failed: {e}")
        return False

    return True

def standby_mode_started():
    global RECONNECTED_CHECK
    logging.info("[Note] Goin on standby mode.")

    # Reset to bot when entering standby - but wait for new state to be initialized
    # Reset to bot when entering standby
    if STATE:
        STATE.current_player_id = STATE.bot_id
        STATE.current_player = None  # Will be updated when new state loads
        logging.info("Reset current_player_id to bot_id for standby mode")

        # Notify websocket clients about the state change
        try:
            from websocket_console import notify_serverstate_change
            notify_serverstate_change()
            logging.info("Sent websocket notification for standby reset")
        except Exception as e:
            logging.error(f"Failed to send websocket notification: {e}")

    STANDBY_START_T = time.time()
    ignore_finish_standbymode = False
    msg_switch_t = 3  # time in seconds to switch between the two standby messages
    last_serverstate_refresh = time.time()
    serverstate_refresh_interval = 10  # Refresh serverstate every 10 seconds during standby

    while (time.time() - STANDBY_START_T) < 60 * STANDBY_TIME:
        if RECONNECTED_CHECK:
            ignore_finish_standbymode = True
            RECONNECTED_CHECK = False
            break

        api.exec_command("team p")

        api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3No active servers. On standby mode.")
        #  api.display_message("No active servers. On standby mode.", time=msg_switch_t + 1)
        time.sleep(msg_switch_t)
        api.exec_command(f"cg_centertime 2;displaymessage 140 10 Use ^3?^7connect ^3ip^7 or ^3?^7restart to continue the bot^3.")
        #  api.display_message("Use ^3?^7connect ^3ip^7 or ^3?^7restart to continue the bot^3.", time=msg_switch_t)
        time.sleep(msg_switch_t)

        # Refresh serverstate periodically during standby mode
        current_time = time.time()
        if current_time - last_serverstate_refresh >= serverstate_refresh_interval:
            try:
                from websocket_console import notify_serverstate_change
                notify_serverstate_change()
                last_serverstate_refresh = current_time
                logging.debug("Refreshed serverstate during standby mode")
            except Exception as e:
                logging.error(f"Failed to refresh serverstate during standby: {e}")

    if not ignore_finish_standbymode:
        standby_mode_finished()


def standby_mode_finished():
    global IGNORE_IPS

    IGNORE_IPS = []

    logging.info("[Note] standby mode finished. Checking for new servers.")

    new_server = servers.get_next_active_server(IGNORE_IPS)

    if new_server is None or new_server == "":
        logging.info("[Note] No Active servers found. Going back to standby mode.")
        standby_mode_started()
        return

    logging.info("[SERVERSTATE] Connecting Now : " + str(new_server))
    connect(new_server)


def validate_state():
    """
    Analyzes the server state data any issues in our current state, specifically for:
    - An idle bot (self-spectating)
    - A lack of players to spec
    - AFK player detection
    - No-specced player detection
    """
    global STATE
    global PAUSE_STATE
    global IGNORE_IPS
    global RECONNECTED_CHECK
    global AFK_COUNTDOWN_ACTIVE
    global AFK_HELP_THREADS

    if STATE is None:
        logging.warning("validate_state called but STATE is None, skipping validation")
        return

    # Clean up AFK flags older than 10 minutes
    current_time = time.time()
    afk_timeout_seconds = 10 * 60  # 10 minutes
    expired_afk_ids = []

    for player_id in list(STATE.afk_ids):
        if player_id in STATE.afk_timestamps:
            time_flagged = current_time - STATE.afk_timestamps[player_id]
            if time_flagged >= afk_timeout_seconds:
                expired_afk_ids.append(player_id)
                STATE.afk_ids.remove(player_id)
                del STATE.afk_timestamps[player_id]

                # Add back to spectatable if player is still on server and not nospec
                player = STATE.get_player_by_id(player_id)
                if player and player.t != '3' and player.c1 not in ['nospec', 'nospecpm']:
                    if player_id not in STATE.spec_ids:
                        STATE.spec_ids.append(player_id)
                        logging.info(f"AFK flag expired for player {player_id} ({player.n}) after 10 minutes - now spectatable")
                        api.exec_command(f"say ^2{player.n} ^7AFK flag cleared - now spectatable again.")
        else:
            # No timestamp found - remove from AFK list (shouldn't happen, but safety check)
            STATE.afk_ids.remove(player_id)
            logging.warning(f"Removed player {player_id} from AFK list - no timestamp found")

    old_player_id = STATE.current_player_id  # Store for timeout cleanup

    # EXISTING DEBUG LOGGING
    # logging.info(f"DEBUG: current_player_id={STATE.current_player_id}, bot_id={STATE.bot_id}")
    # logging.info(f"DEBUG: spectating_self check: {STATE.current_player_id == STATE.bot_id}")
    # if STATE.current_player:
        # logging.info(f"DEBUG: current_player name: {STATE.current_player.n}")
    # else:
        # logging.info("DEBUG: current_player is None")
    
    # logging.info(f"DEBUG: spec_ids={STATE.spec_ids}")
    # logging.info(f"DEBUG: nospec_ids={STATE.nospec_ids}")
    # logging.info(f"DEBUG: total players={len(STATE.players)}")
    # for player in STATE.players:
        # logging.info(f"DEBUG: Player {player.id}: {player.n}, team={player.t}, c1={player.c1}")
    
    # ADD THESE NEW DEBUG LINES HERE:
    # logging.info(f"DEBUG: Looking for player with ID {STATE.current_player_id}")
    # logging.info(f"DEBUG: get_player_by_id result: {STATE.get_player_by_id(STATE.current_player_id)}")
    
    # Wrap the team check in try-catch to prevent crashing the main loop
    try:
        check_bot_team_status()
    except Exception as e:
        logging.error(f"Error in team status check: {e}")
        # Continue with normal validation even if team check fails
    
    # Check if we're spectating ourselves - prioritize ID check as it's more reliable
    spectating_self = STATE.current_player_id == STATE.bot_id

    # Additional check using dfn if bot player exists and ID check wasn't sufficient
    if not spectating_self and STATE.get_player_by_id(STATE.bot_id) is not None:
        spectating_self = STATE.curr_dfn == STATE.get_player_by_id(STATE.bot_id).dfn

    # ALSO check if we're spectating a spectator (team 3) or a disconnected player - bot should only spectate active players
    if not spectating_self and STATE.current_player_id != STATE.bot_id:
        current_player = STATE.get_player_by_id(STATE.current_player_id)
        if current_player is None:
            # Spectating a player who no longer exists (disconnected)
            logging.info(f"SPECTATING_DISCONNECTED DETECTED: Currently spectating ID {STATE.current_player_id} who no longer exists. Switching to active player.")
            spectating_self = True  # Treat this like spectating self - need to switch away
        elif current_player.t == '3':
            # Spectating a spectator (team 3)
            logging.info(f"SPECTATING_SPECTATOR DETECTED: Currently spectating {current_player.n} (ID: {STATE.current_player_id}) who is team 3 (spectator). Switching to active player.")
            spectating_self = True  # Treat this like spectating self - need to switch away

    # DEBUG: Log spectating_self detection details when potentially problematic
    if STATE.current_player_id == STATE.bot_id and not spectating_self:
        logging.warning(f"SPECTATE_SELF DEBUG: Detection mismatch - current_player_id={STATE.current_player_id}, bot_id={STATE.bot_id}, but spectating_self={spectating_self}")
        bot_player = STATE.get_player_by_id(STATE.bot_id)
        logging.warning(f"SPECTATE_SELF DEBUG: Bot player object exists: {bot_player is not None}, curr_dfn: {STATE.curr_dfn}")
        if bot_player:
            logging.warning(f"SPECTATE_SELF DEBUG: Bot player dfn: {bot_player.dfn}, dfn match: {STATE.curr_dfn == bot_player.dfn}")

    # Current player spectated has turned on the no-spec system
    # Only consider players in nospec_ids as truly nospec (not team 3 spectators)
    spectating_nospec = STATE.current_player_id in STATE.nospec_ids
    if spectating_nospec:
        logging.info(f"DEBUG: spectating_nospec=True for player {STATE.current_player_id} - in nospec_ids: {STATE.nospec_ids}")
    elif STATE.current_player_id not in STATE.spec_ids and STATE.current_player_id != STATE.bot_id:
        current_player = STATE.get_player_by_id(STATE.current_player_id)
        if current_player:
            logging.info(f"DEBUG: Player {STATE.current_player_id} ({current_player.n}) not in spec_ids but not nospec - team: {current_player.t}, c1: {current_player.c1}")

    # Get the AFK timeout for current player (could be extended)
    current_afk_timeout = STATE.get_afk_timeout_for_player(STATE.current_player_id)

    # The player that we are spectating has been AFK for their custom limit
    spectating_afk = STATE.afk_counter >= current_afk_timeout

    # DEBUG: Log the key conditions for switching logic (only when the switch snapshot changes)
    # Build a normalized switch snapshot. Normalize free spectators by id as ints.
    try:
        free_spec_ids = tuple(sorted(int(p.id) for p in STATE.players if getattr(p, 't', None) == '3'))
    except Exception:
        free_spec_ids = tuple(sorted(str(p.id) for p in STATE.players if getattr(p, 't', None) == '3'))

    switch_snapshot = (
        int(STATE.current_player_id) if STATE.current_player_id is not None else None,
        _normalize_ids(STATE.spec_ids),
        _normalize_ids(STATE.nospec_ids),
        _normalize_ids(STATE.afk_ids),
        free_spec_ids,
    )

    from config import LOG_ONLY_CHANGES
    global LAST_SWITCH_SNAPSHOT
    should_log_switch = False
    if not LOG_ONLY_CHANGES or LAST_SWITCH_SNAPSHOT is None or LAST_SWITCH_SNAPSHOT != switch_snapshot:
        should_log_switch = True

    if should_log_switch:
        logging.info(f"SWITCH DEBUG: Conditions - spectating_self={spectating_self}, spectating_nospec={spectating_nospec}, spectating_afk={spectating_afk}")
        logging.info(f"SWITCH DEBUG: current_player_id={STATE.current_player_id}, bot_id={STATE.bot_id}, afk_counter={STATE.afk_counter}/{current_afk_timeout}")
        if LOG_ONLY_CHANGES:
            # Remember this snapshot so identical future ticks won't re-log
            LAST_SWITCH_SNAPSHOT = switch_snapshot

    # AFK player pre-processing
    if spectating_afk:
        try:
            STATE.spec_ids.remove(STATE.current_player_id)  # Remove afk player from list of spec-able players
            # Add them to the afk list
            was_already_afk = STATE.current_player_id in STATE.afk_ids
            if STATE.current_player_id not in STATE.afk_ids:
                STATE.afk_ids.append(STATE.current_player_id)
                STATE.afk_timestamps[STATE.current_player_id] = time.time()  # Record when flagged

            if not was_already_afk:
                # Newly flagged as AFK - notify in chat
                afk_player = STATE.get_player_by_id(STATE.current_player_id)
                player_name = afk_player.n if afk_player else f"ID{STATE.current_player_id}"
                logging.info(f"Added player {STATE.current_player_id} to AFK list")
                api.exec_command(f"say ^1{player_name} ^7flagged as AFK - ignoring for 10 minutes.")

            if not PAUSE_STATE:
                logging.info("AFK. Switching...")
                api.display_message("^3AFK detected. ^7Switching to the next player.", time=5)
                STATE.afk_counter = 0  # Reset AFK strike counter for next player
                # Reset the timeout for this player back to default when switching due to AFK
                if str(STATE.current_player_id) in STATE.player_afk_timeouts:
                    del STATE.player_afk_timeouts[str(STATE.current_player_id)]
                    logging.info(f"Reset AFK timeout for player {STATE.current_player_id} back to default (AFK timeout)")
        except ValueError:
            pass

    # Next player choice logic
    if spectating_self or spectating_nospec or spectating_afk:
        if should_log_switch:
            logging.info(f"SWITCH DEBUG: Triggering player switch - spectating_self={spectating_self}, spectating_nospec={spectating_nospec}, spectating_afk={spectating_afk}")
            logging.info(f"SWITCH DEBUG: Available spec_ids: {STATE.spec_ids}")
        # Find someone else to spec - avoid following ourselves if possible
        if STATE.spec_ids:
            follow_id = random.choice(STATE.spec_ids)
        else:
            # No valid spectate targets available - this should trigger a different behavior
            # rather than following ourselves and getting stuck
            follow_id = None
        if should_log_switch:
            logging.info(f"SWITCH DEBUG: Selected follow_id: {follow_id}")

        if follow_id is not None and follow_id != STATE.bot_id:  # Found someone successfully, follow this person
            # Reset timeout for old player back to default when switching to different player
            if old_player_id != follow_id and old_player_id and str(old_player_id) in STATE.player_afk_timeouts:
                del STATE.player_afk_timeouts[str(old_player_id)]
                logging.info(f"Reset AFK timeout for player {old_player_id} back to default (player switch)")

            if spectating_nospec:
                if not PAUSE_STATE and not spectating_self:
                    # DEBUG: Log detailed information about why player is not specable
                    logging.info(f"DEBUG: Player {STATE.current_player_id} not specable - spec_ids: {STATE.spec_ids}, afk_ids: {STATE.afk_ids}")
                    
                    # Determine WHY player is not specable for better error message
                    target_player = STATE.get_player_by_id(STATE.current_player_id)
                    if target_player:
                        logging.info(f"DEBUG: Target player {STATE.current_player_id} found - t: '{target_player.t}', c1: '{target_player.c1}', dfn: '{target_player.dfn}'")
                        if target_player.t == '3':  # Player is a spectator
                            logging.info('Free spectator detected. Switching...')
                            api.display_message("^7Can't spec free spectators. Switching.")
                        elif target_player.c1 in ['nospec', 'nospecpm']:  # Actual nospec
                            logging.info('Nospec detected. Switching...')
                            api.display_message("^7Nospec detected. Switching.")
                        else:  # Other reason (shouldn't happen but fallback)
                            logging.info(f'DEBUG: Player not specable for unknown reason - t: "{target_player.t}", c1: "{target_player.c1}", not in spec_ids')
                            logging.info('Player not specable. Switching...')
                            api.display_message("^7Player unavailable. Switching.")
                    else:
                        # Fallback if player object not found
                        logging.info(f'DEBUG: Player {STATE.current_player_id} object not found in player list')
                        logging.info('Player not specable. Switching...')
                        api.display_message("^7Player unavailable. Switching.")

            display_player_name(follow_id)
            logging.info(f"SWITCH DEBUG: Executing 'follow {follow_id}' command")
            api.exec_command(f"follow {follow_id}")
            STATE.current_player_id = int(follow_id)
            STATE.current_player = STATE.get_player_by_id(int(follow_id))
            STATE.idle_counter = 0  # Reset idle strike flag since a followable non-bot id was found.
            STATE.afk_counter = 0

            # If this player was previously in failed/excluded lists, clear them since we're attempting to spectate
            global FAILED_FOLLOW_ATTEMPTS, PERMANENTLY_EXCLUDED
            if follow_id in FAILED_FOLLOW_ATTEMPTS:
                del FAILED_FOLLOW_ATTEMPTS[follow_id]
            if follow_id in PERMANENTLY_EXCLUDED:
                PERMANENTLY_EXCLUDED.discard(follow_id)
                logging.info(f"Removed player {follow_id} from permanent exclusion list - retrying spectate")

            logging.info(f"SWITCH DEBUG: Successfully switched to player {follow_id} ({STATE.current_player.n if STATE.current_player else 'Unknown'})")
            # After a successful manual switch, update the snapshot to reflect the new state
            LAST_SWITCH_SNAPSHOT = switch_snapshot
            return  # CRITICAL: Exit validation after successful switch

        else:  # No valid targets available or only found ourselves to spec.
            if STATE.current_player_id != STATE.bot_id:  # Stop spectating player, go to free spec mode instead.
                # Reset timeout when switching to bot
                if str(STATE.current_player_id) in STATE.player_afk_timeouts:
                    del STATE.player_afk_timeouts[str(STATE.current_player_id)]
                    logging.info(f"Reset AFK timeout for player {STATE.current_player_id} back to default (switching to bot)")

                # If no valid follow_id, just switch to free spec mode using bot ID
                target_id = follow_id if follow_id is not None else STATE.bot_id
                if should_log_switch:
                    logging.info(f"SWITCH DEBUG: No valid targets, switching to free spec mode using ID {target_id}")
                api.exec_command(f"follow {target_id}")
                STATE.current_player_id = STATE.bot_id
            else:  # Was already spectating self. This is an idle strike
                STATE.idle_counter += 1

                # DEBUG: Add comprehensive logging for why we're not spectating anyone
                logging.info(f"IDLE DEBUG: No spectatable players found - reason analysis:")
                logging.info(f"IDLE DEBUG: Total players on server: {len(STATE.players)}")
                logging.info(f"IDLE DEBUG: Spectatable players: {[(STATE.get_player_by_id(pid).n if STATE.get_player_by_id(pid) else 'Unknown', pid) for pid in STATE.spec_ids]}")
                logging.info(f"IDLE DEBUG: NoSpec players: {[(STATE.get_player_by_id(pid).n if STATE.get_player_by_id(pid) else 'Unknown', pid) for pid in STATE.nospec_ids]}")
                logging.info(f"IDLE DEBUG: AFK players: {[(STATE.get_player_by_id(pid).n if STATE.get_player_by_id(pid) else 'Unknown', pid) for pid in STATE.afk_ids]}")
                logging.info(f"IDLE DEBUG: Free spectators: {[(p.n, p.id) for p in STATE.players if p.t == '3']}")
                logging.info(f"IDLE DEBUG: Bot ID: {STATE.bot_id}, Current player ID: {STATE.current_player_id}")

                logging.info(f"Not spectating. Strike {STATE.idle_counter}/{IDLE_TIMEOUT}")
                if not PAUSE_STATE:
                    api.display_message(f"^3Strike {STATE.idle_counter}/{IDLE_TIMEOUT}", time=1)

            if STATE.idle_counter >= IDLE_TIMEOUT or spectating_afk:
                # There's been no one on the server for a while or only afks. Switch servers.
                # Build detailed farewell message explaining why bot is leaving
                farewell_parts = []

                # List AFK players with names
                if STATE.afk_ids:
                    afk_names = [STATE.get_player_by_id(pid).n if STATE.get_player_by_id(pid) else f"ID{pid}" for pid in STATE.afk_ids]
                    farewell_parts.append(f"^1AFK: ^7{', '.join(afk_names)}")

                # List Nospec players with names
                if STATE.nospec_ids:
                    nospec_names = [STATE.get_player_by_id(pid).n if STATE.get_player_by_id(pid) else f"ID{pid}" for pid in STATE.nospec_ids]
                    farewell_parts.append(f"^1Nospec: ^7{', '.join(nospec_names)}")

                # List free spectators (team 3) with names
                free_specs = [p.n for p in STATE.players if p.t == '3' and p.id != STATE.bot_id]
                if free_specs:
                    farewell_parts.append(f"^1Spectating: ^7{', '.join(free_specs)}")

                # Build final message - if message gets too long, split into multiple says
                if farewell_parts:
                    reason_msg = " | ".join(farewell_parts)
                    # Quake 3 say command has ~150 character limit, so split if needed
                    if len(reason_msg) > 120:
                        # Send reason details first
                        api.exec_command(f"say {reason_msg}")
                        time.sleep(0.5)
                        api.exec_command("say ^3Switching servers. Farewell.")
                    else:
                        api.exec_command(f"say {reason_msg} ^3- Farewell.")
                elif len(STATE.players) <= 1:  # Only bot left
                    api.exec_command("say ^7No active players remaining. ^3Farewell.")
                else:
                    # Fallback (shouldn't happen, but just in case)
                    api.exec_command("say ^7No spectatable players available. ^3Farewell.")

                # DETAILED DEBUG: Print complete server state before leaving
                logging.info("=" * 80)
                logging.info("LEAVING SERVER - DETAILED STATE DUMP:")
                logging.info(f"Reason: {'spectating_afk=True' if spectating_afk else f'idle_counter={STATE.idle_counter}/{IDLE_TIMEOUT}'}")
                logging.info(f"Server IP: {STATE.ip}")
                logging.info(f"Total players on server: {len(STATE.players)}")
                logging.info("-" * 80)

                # Print each player with full details
                for player in STATE.players:
                    status_flags = []
                    if player.id == STATE.bot_id:
                        status_flags.append("BOT")
                    if player.id in STATE.spec_ids:
                        status_flags.append("SPECTATABLE")
                    if player.id in STATE.nospec_ids:
                        status_flags.append("NOSPEC")
                    if player.id in STATE.afk_ids:
                        # Show how long they've been AFK
                        if player.id in STATE.afk_timestamps:
                            afk_duration = int(time.time() - STATE.afk_timestamps[player.id])
                            status_flags.append(f"AFK({afk_duration}s)")
                        else:
                            status_flags.append("AFK(no timestamp)")
                    if player.t == '3':
                        status_flags.append("FREE_SPEC")

                    status = f"[{', '.join(status_flags)}]" if status_flags else "[UNKNOWN_STATUS]"
                    logging.info(f"  Player ID {player.id}: '{player.n}' - Team: {player.t}, c1: '{player.c1}' {status}")

                logging.info("-" * 80)
                logging.info(f"Spectatable IDs (spec_ids): {STATE.spec_ids}")
                logging.info(f"Nospec IDs (nospec_ids): {STATE.nospec_ids}")
                logging.info(f"AFK IDs (afk_ids): {STATE.afk_ids}")
                logging.info(f"Current player ID being spectated: {STATE.current_player_id}")
                logging.info(f"Bot ID: {STATE.bot_id}")
                logging.info("=" * 80)

                # Wait 2 seconds before searching for new server and connecting
                time.sleep(2)

                IGNORE_IPS.append(STATE.ip) if STATE.ip not in IGNORE_IPS and STATE.ip != "" else None
                new_ip = servers.get_next_active_server(IGNORE_IPS)
                logging.info(f"Next active server found: {new_ip}")

                if bool(new_ip):
                    connect(new_ip)
                    return
                else:  # No ip left to connect to, go on standby mode.
                    api.exec_command("map st1")
                    IGNORE_IPS = []
                    RECONNECTED_CHECK = False
                    standby_mode_started()

        STATE.current_player = STATE.get_player_by_id(STATE.current_player_id)

    else:  # AFK detection
        # Build a compact AFK snapshot that represents the AFK-related state we care about.
        # Normalize lists (sort) so ordering changes don't cause log noise.
        afk_list_sorted = tuple(sorted(STATE.afk_ids)) if STATE.afk_ids else ()
        current_afk_snapshot = (
            int(STATE.current_player_id) if STATE.current_player_id is not None else None,
            int(STATE.afk_counter),
            int(current_afk_timeout),
            afk_list_sorted,
        )

        # Only log the AFK entering/checking messages when the snapshot changed or when we cross important thresholds.
        should_log_afk = False
        global LAST_AFK_SNAPSHOT
        if LAST_AFK_SNAPSHOT is None or LAST_AFK_SNAPSHOT != current_afk_snapshot:
            should_log_afk = True
        # Also always log when reaching the notification threshold (first time) or when multiples occur as before
        if STATE.afk_counter >= 10 and (STATE.afk_counter - 10) % 5 == 0:
            should_log_afk = True

        inputs = STATE.get_inputs()

        # Only log when AFK counter changes (increment/reset) or thresholds are hit
        previous_afk = LAST_AFK_SNAPSHOT[1] if LAST_AFK_SNAPSHOT is not None else None

        if inputs == '':
            # Empty key presses. This is an AFK strike.
            STATE.afk_counter += 1
            # Log only when the counter actually changed
            if previous_afk is None or STATE.afk_counter != previous_afk:
                # Only show increment logs for multiples of 5 to reduce noise
                if STATE.afk_counter % 5 == 0:
                    logging.info(f"AFK DEBUG: No inputs detected, incremented counter to {STATE.afk_counter}")
            
            # Show notifications starting from strike 10, then every 5 strikes: 10, 15, 20, 25, 30...
            if STATE.afk_counter >= 10 and (STATE.afk_counter - 10) % 5 == 0:  # Every 5 strikes after 10: 10, 15, 20, 25, 30...
                remaining_time = (current_afk_timeout - STATE.afk_counter) * 2
                if remaining_time > 0:
                    logging.info(f"AFK detected. Strike {STATE.afk_counter}/{current_afk_timeout}")
                    
                    # Send both in-game and Twitch chat notification
                    player_name = STATE.current_player.n if STATE.current_player else "Unknown"
                    api.display_message(f" AFK detected. Switching in {remaining_time} seconds.", time=5)
                    
                    # Also send to Twitch chat through the chat bridge system
                    try:
                        import console
                        import json
                        afk_msg = {
                            'action': 'afk_notification',
                            'message': f"AFK detected for {player_name}: {STATE.afk_counter}/{current_afk_timeout} strikes - switching in ~{remaining_time}s"
                        }
                        console.WS_Q.put(json.dumps(afk_msg))
                    except Exception as e:
                        logging.error(f"Failed to send AFK notification to Twitch: {e}")

        else:
            # Activity detected, reset AFK strike counter for current player only
            if STATE.afk_counter != 0:
                # Only log on counter reset
                if STATE.afk_counter >= 15:
                    api.display_message("Activity detected. ^3AFK counter aborted.")
                    logging.info("Activity detected. AFK counter aborted.")
                # Only log debug message if counter was significant (5 or more)
                if STATE.afk_counter >= 5:
                    logging.info(f"AFK DEBUG: Activity detected, resetting counter from {STATE.afk_counter} to 0")

            STATE.afk_counter = 0
            # Only remove current player from AFK list, keep other AFK players
            if STATE.current_player_id in STATE.afk_ids:
                STATE.afk_ids.remove(STATE.current_player_id)
                # Also clean up timestamp
                if STATE.current_player_id in STATE.afk_timestamps:
                    del STATE.afk_timestamps[STATE.current_player_id]
                logging.info(f"Removed player {STATE.current_player_id} from AFK list")
            IGNORE_IPS = []
            # CANCEL ANY ACTIVE AFK COUNTDOWNS
            AFK_COUNTDOWN_ACTIVE = False
            AFK_HELP_THREADS.clear()
            # DO NOT reset timeout when player becomes active - keep extended timeout until player switch
            # The timeout will only be reset when switching to a different player (handled above)

        # Save snapshot after processing so subsequent ticks can be compared
        LAST_AFK_SNAPSHOT = current_afk_snapshot

def switch_to_player(follow_id):
    """Helper function to handle player switching and timeout cleanup"""
    old_player_id = STATE.current_player_id
    
    # Reset timeout for old player back to default when switching away
    if old_player_id and str(old_player_id) in STATE.player_afk_timeouts:
        del STATE.player_afk_timeouts[str(old_player_id)]
        logging.info(f"Reset AFK timeout for player {old_player_id} back to default (player switch)")
    
    # Switch to new player
    STATE.current_player_id = follow_id
    STATE.current_player = STATE.get_player_by_id(follow_id)

def connect(ip, caller=None):
    """
    Handles connection to a server and re-attempts if connection is not resolved.
    """
    global PAUSE_STATE
    global STATE_INITIALIZED
    global CONNECTING
    global IGNORE_IPS
    global CURRENT_IP
    global RECONNECTED_CHECK
    global AFK_COUNTDOWN_ACTIVE
    global AFK_HELP_THREADS
    global LAST_GREETING_SERVER

    # ABORT ALL AFK COUNTDOWNS AND HELP MESSAGES IMMEDIATELY
    AFK_COUNTDOWN_ACTIVE = False  # This will stop any running countdown threads
    
    # Cancel any pending AFK help messages
    for thread in AFK_HELP_THREADS:
        if thread.is_alive():
            logging.info("Cancelling AFK help thread due to server connection")
            # Threads will check AFK_COUNTDOWN_ACTIVE flag and exit
    AFK_HELP_THREADS.clear()

    # Check if this is a NEW server connection or reconnection to same server
    is_new_server = (CURRENT_IP != ip)

    STATE_INITIALIZED = False
    logging.info(f"Connecting to {ip}...")
    PAUSE_STATE = True
    CONNECTING = True
    
    if STATE:  # Check if STATE exists before accessing it
        STATE.idle_counter = 0
        STATE.afk_counter = 0
        STATE.afk_ids = []
        STATE.afk_timestamps = {}  # Clear AFK timestamps on new connection

    if caller is not None:
        if STATE:
            STATE.connect_msg = f"^7Brought by ^3{caller}"
        IGNORE_IPS = []

    RECONNECTED_CHECK = True
    CURRENT_IP = ip

    # Store whether this should trigger a greeting (only for new servers)
    if is_new_server:
        logging.info(f"New server connection detected: {ip}")
    else:
        logging.info(f"Reconnecting to same server: {ip}")

    api.exec_command("connect " + ip, verbose=False)

def attempt_state_resume():
    """
    Try to resume normal state without reconnecting
    This checks if the connection actually worked but we just got stuck
    """
    global PAUSE_STATE, CONNECTING, CONNECTION_START_TIME
    global STATE_PAUSED_COUNTER, LAST_PAUSE_LOG_TIME
    
    try:
        logging.info("Attempting to resume normal state...")
        
        # Try to get fresh server info to see if we're actually connected
        api.exec_command("team s;svinfo_report serverstate.txt;svinfo_report initialstate.txt")
        
        # Wait a moment for reports to generate
        time.sleep(2)
        
        # Check if we can read valid server info
        if new_report_exists(config.STATE_REPORT_P):
            server_info, players, num_players = get_svinfo_report(config.STATE_REPORT_P)
            
            if server_info and players:
                logging.info("State resume successful - connection was actually working!")

                # Resume normal operation
                PAUSE_STATE = False
                STATE_PAUSED_COUNTER = 0
                LAST_PAUSE_LOG_TIME = 0
                CONNECTING = False
                CONNECTION_START_TIME = None
                
                # Reinitialize state properly
                initialize_state(True)
                
                # Mark recovery as successful
                reset_recovery_state()
                return True
        
        logging.info("State resume failed - no valid server data")
        return False
        
    except Exception as e:
        logging.error(f"Error during state resume attempt: {e}")
        return False

def smart_connection_recovery(reason="Unknown"):
    """
    Smart recovery system that tries multiple strategies before giving up:
    1. First attempt: Try to resume normal state (reinitialize)
    2-4. Attempts 2-4: Reconnect to same server (3 retry attempts)
    5. Fifth attempt: Try different server  
    6+. Final fallback: Standby mode
    """
    global RECOVERY_IN_PROGRESS, RECOVERY_ATTEMPTS, LAST_RECOVERY_TIME
    global PAUSE_STATE, CONNECTING, CONNECTION_START_TIME
    
    current_time = time.time()
    
    # Check if recovery has been stuck for too long (2 minutes absolute timeout)
    if RECOVERY_IN_PROGRESS and current_time - LAST_RECOVERY_TIME > 120:
        logging.error(f"RECOVERY DEADLOCK: Recovery stuck for 120s, forcing full reset. Reason: {reason}")
        reset_recovery_state()
        PAUSE_STATE = False
        CONNECTING = False
        CONNECTION_START_TIME = None
        api.exec_command("map st1")
        import threading
        standby_thread = threading.Thread(target=standby_mode_started, daemon=True)
        standby_thread.start()
        return
    
    # Prevent multiple simultaneous recoveries (but allow timeout-forced progression)
    if RECOVERY_IN_PROGRESS and not reason.startswith("Forced progression"):
        time_stuck = current_time - LAST_RECOVERY_TIME
        logging.warning(f"RECOVERY BLOCKED: Already in progress for {time_stuck:.0f}s, ignoring: {reason}")
        return
    
    # Check if this is a critical crash that should bypass cooldown
    is_critical_crash = any(crash_indicator in reason for crash_indicator in [
        "ACCESS_VIOLATION", 
        "Exception Code:", 
        "Signal caught",
        "forcefully unloading cgame vm",
        "Game error: Exception Code:",
        "Game error: ACCESS_VIOLATION"
    ])
    
    # Cooldown check - SKIP for critical crashes
    if not is_critical_crash and current_time - LAST_RECOVERY_TIME < RECOVERY_COOLDOWN:
        logging.info(f"Recovery on cooldown, ignoring: {reason}")
        return
    
    # For critical crashes, log that we're bypassing cooldown
    if is_critical_crash and current_time - LAST_RECOVERY_TIME < RECOVERY_COOLDOWN:
        logging.warning(f"Critical crash detected - bypassing recovery cooldown: {reason}")
    
    # Determine recovery strategy based on crash type
    is_access_violation = "ACCESS_VIOLATION" in reason
    max_attempts = 6 if is_access_violation else MAX_RECOVERY_ATTEMPTS
    
    RECOVERY_IN_PROGRESS = True
    LAST_RECOVERY_TIME = current_time
    RECOVERY_ATTEMPTS += 1
    
    # ADD ENHANCED LOGGING HERE
    logging.error(f"RECOVERY START: Attempt #{RECOVERY_ATTEMPTS}, Reason: {reason}")
    logging.error(f"RECOVERY STATE: PAUSE={PAUSE_STATE}, CONNECTING={CONNECTING}, VID_RESTART={VID_RESTARTING}")
    logging.error(f"RECOVERY TIMING: Last={LAST_RECOVERY_TIME}, Current={current_time}")
    if is_access_violation:
        logging.error(f"ACCESS_VIOLATION detected - using extended recovery (max {max_attempts} attempts)")
    
    try:
        if RECOVERY_ATTEMPTS == 1:
            # First attempt: Try to resume normal state
            logging.error("RECOVERY ATTEMPT 1: Trying state resume")
            if attempt_state_resume():
                return  # Success, exit recovery
            
        elif RECOVERY_ATTEMPTS <= (5 if is_access_violation else 4):
            # Attempts 2-5 for ACCESS_VIOLATION, 2-4 for other crashes: Reconnect to same server 
            logging.error(f"RECOVERY ATTEMPT {RECOVERY_ATTEMPTS}: Reconnecting to same server")
            if CURRENT_IP:
                # Reset connection state - be more aggressive about cleanup
                PAUSE_STATE = True
                CONNECTING = True
                CONNECTION_START_TIME = time.time()
                
                # More robust reconnect - disconnect first, then reconnect
                api.exec_command("disconnect", verbose=False)
                time.sleep(3)  # 3 second delay between disconnect and reconnect
                api.exec_command("connect " + CURRENT_IP, verbose=False)
                start_connection_monitor()
            else:
                # No current IP, skip to different server attempt
                RECOVERY_ATTEMPTS = 4  # Skip to attempt 5 (different server)
                smart_connection_recovery("No current IP for reconnect")
                return
                
        elif RECOVERY_ATTEMPTS == (6 if is_access_violation else 5):
            # Try different server (attempt 6 for ACCESS_VIOLATION, attempt 5 for others)
            logging.error(f"RECOVERY ATTEMPT {RECOVERY_ATTEMPTS}: Trying different server")
            if CURRENT_IP:
                IGNORE_IPS.append(CURRENT_IP)
            
            new_ip = servers.get_next_active_server(IGNORE_IPS)
            if new_ip and new_ip != CURRENT_IP:
                logging.info(f"Recovery: trying different server {new_ip}")
                time.sleep(2)  # Brief pause before retry
                enhanced_connect(new_ip)
            else:
                # No other servers, go to final fallback
                RECOVERY_ATTEMPTS += 1
                smart_connection_recovery("No other servers available")
                return
                
        else:
            # Final fallback: Standby mode
            logging.error("RECOVERY ATTEMPT 6+: Entering standby mode")
            reset_recovery_state()
            IGNORE_IPS = []
            PAUSE_STATE = False
            CONNECTING = False
            CONNECTION_START_TIME = None
            api.exec_command("map st1")  # Load local map
            standby_mode_started()
            return
            
        # Start timeout monitor for this recovery attempt
        logging.error(f"RECOVERY TIMEOUT: Starting 60s monitor for attempt {RECOVERY_ATTEMPTS}")
        start_recovery_timeout()
        
    except Exception as e:
        logging.critical(f"RECOVERY EXCEPTION: Error during attempt {RECOVERY_ATTEMPTS}: {e}")
        # Force standby on any exception
        reset_recovery_state()
        PAUSE_STATE = False
        api.exec_command("map st1")

def check_recovery_deadlock():
    """Check if recovery system is deadlocked and force reset if needed"""
    global RECOVERY_IN_PROGRESS, LAST_RECOVERY_TIME, PAUSE_STATE
    
    if RECOVERY_IN_PROGRESS:
        stuck_time = time.time() - LAST_RECOVERY_TIME
        if stuck_time > 150:  # 2.5 minutes absolute deadlock protection
            logging.critical(f"RECOVERY DEADLOCK DETECTED: Stuck for {stuck_time:.0f}s - forcing emergency reset")
            reset_recovery_state()
            PAUSE_STATE = False
            api.exec_command("map st1")
            return True
    return False

def reset_recovery_state():
    """Reset recovery tracking variables"""
    global RECOVERY_IN_PROGRESS, RECOVERY_ATTEMPTS, RECOVERY_TIMEOUT_ACTIVE
    RECOVERY_IN_PROGRESS = False
    RECOVERY_ATTEMPTS = 0
    RECOVERY_TIMEOUT_ACTIVE = False
    logging.info("Recovery state reset")

def start_recovery_timeout():
    """Start a timeout for the current recovery attempt"""
    global RECOVERY_TIMEOUT_ACTIVE
    
    # Prevent multiple timeout threads
    if RECOVERY_TIMEOUT_ACTIVE:
        logging.debug("Recovery timeout already active, skipping new timeout thread")
        return
        
    RECOVERY_TIMEOUT_ACTIVE = True
    
    def recovery_timeout_worker():
        import time
        time.sleep(60)  # Give each recovery attempt 60 seconds
        
        global RECOVERY_IN_PROGRESS, RECOVERY_ATTEMPTS, PAUSE_STATE, CONNECTING, RECOVERY_TIMEOUT_ACTIVE
        
        if RECOVERY_IN_PROGRESS:
            logging.error(f"RECOVERY TIMEOUT: Attempt {RECOVERY_ATTEMPTS} stuck for 60s, forcing progression")
            
            # Force progression to next attempt
            if RECOVERY_ATTEMPTS >= MAX_RECOVERY_ATTEMPTS:
                logging.error("RECOVERY TIMEOUT: Max attempts reached, forcing standby")
                reset_recovery_state()
                PAUSE_STATE = False
                CONNECTING = False
                api.exec_command("map st1")
                import threading
                standby_thread = threading.Thread(target=standby_mode_started, daemon=True)
                standby_thread.start()
            else:
                # DIRECTLY FORCE NEXT ATTEMPT - don't call smart_connection_recovery
                logging.error(f"RECOVERY TIMEOUT: Directly forcing attempt {RECOVERY_ATTEMPTS + 1}")
                RECOVERY_ATTEMPTS += 1  # Increment attempt counter
                
                # Directly handle next attempt based on attempt number
                if RECOVERY_ATTEMPTS == 2:
                    # Attempt 2: Reconnect to same server
                    logging.error("TIMEOUT RECOVERY: Attempt 2 - Reconnecting to same server")
                    if CURRENT_IP:
                        PAUSE_STATE = True
                        CONNECTING = True
                        CONNECTION_START_TIME = time.time()
                        api.exec_command("reconnect", verbose=False)
                        start_connection_monitor()
                        # DON'T call start_recovery_timeout() here - would create infinite timeout threads
                    else:
                        # Skip to next attempt
                        smart_connection_recovery("No current IP for reconnect")
                        
                elif RECOVERY_ATTEMPTS == 3:
                    # Attempt 3: Try different server
                    logging.error("TIMEOUT RECOVERY: Attempt 3 - Trying different server")
                    if CURRENT_IP:
                        IGNORE_IPS.append(CURRENT_IP)
                    
                    new_ip = servers.get_next_active_server(IGNORE_IPS)
                    if new_ip and new_ip != CURRENT_IP:
                        logging.info(f"TIMEOUT RECOVERY: trying different server {new_ip}")
                        time.sleep(2)
                        enhanced_connect(new_ip)
                    else:
                        # No other servers, go to standby
                        logging.error("TIMEOUT RECOVERY: No other servers, forcing standby")
                        reset_recovery_state()
                        PAUSE_STATE = False
                        CONNECTING = False
                        api.exec_command("map st1")
                        import threading
                        standby_thread = threading.Thread(target=standby_mode_started, daemon=True)
                        standby_thread.start()
                else:
                    # Attempt 4+: Force standby
                    logging.error("TIMEOUT RECOVERY: Max attempts exceeded, forcing standby")
                    reset_recovery_state()
                    PAUSE_STATE = False
                    CONNECTING = False
                    api.exec_command("map st1")
                    import threading
                    standby_thread = threading.Thread(target=standby_mode_started, daemon=True)
                    standby_thread.start()
        else:
            # Recovery completed while we were waiting, clear timeout flag
            RECOVERY_TIMEOUT_ACTIVE = False
    
    timeout_thread = threading.Thread(target=recovery_timeout_worker, daemon=True)
    timeout_thread.start()

def enhanced_connect(ip, caller=None):
    """Enhanced connect function with better timeout handling"""
    global PAUSE_STATE, CONNECTING, CONNECTION_START_TIME, CURRENT_IP
    global AFK_COUNTDOWN_ACTIVE, AFK_HELP_THREADS, RECOVERY_IN_PROGRESS
    global STATE_INITIALIZED, RECONNECTED_CHECK

    # Reset recovery state for new connections
    if ip != CURRENT_IP:
        reset_recovery_state()

    # Record connection start time - BUT don't reset if we're already connecting to same server
    # This prevents timeout bypass when user spam-reconnects to same hung server
    if CONNECTION_START_TIME is None or ip != CURRENT_IP or not (PAUSE_STATE or CONNECTING):
        CONNECTION_START_TIME = time.time()
        logging.info(f"Connection timer started for {ip}")
    else:
        elapsed = time.time() - CONNECTION_START_TIME
        logging.warning(f"Reconnecting to same server while already stuck - keeping original timer (elapsed: {elapsed:.0f}s)")
    
    # Cancel any AFK operations
    AFK_COUNTDOWN_ACTIVE = False
    AFK_HELP_THREADS.clear()
    
    # Set connection state
    is_new_server = (CURRENT_IP != ip)
    STATE_INITIALIZED = False
    logging.info(f"Connecting to {ip}...")
    PAUSE_STATE = True
    CONNECTING = True
    CURRENT_IP = ip

    # IMPORTANT: Set console pause timer so health check can detect stuck connections
    # Even if game stops outputting console lines, the health check will still work
    import console
    if console.PAUSE_STATE_START_TIME is None:
        console.PAUSE_STATE_START_TIME = time.time()
        logging.info("Pause timer initialized for connection timeout detection")
    
    if STATE:
        STATE.idle_counter = 0
        STATE.afk_counter = 0
        STATE.afk_ids = []
        STATE.afk_timestamps = {}  # Clear AFK timestamps on reconnection

    if caller is not None:
        if STATE:
            STATE.connect_msg = f"^7Brought by ^3{caller}"
        IGNORE_IPS = []

    RECONNECTED_CHECK = True
    
    # Start connection monitor
    start_connection_monitor()
    
    # Execute connection
    api.exec_command("connect " + ip, verbose=False)

def start_connection_monitor():
    """Start a background thread to monitor connection timeout - checks periodically"""
    def monitor_connection():
        global CONNECTION_START_TIME, PAUSE_STATE, CONNECTING

        # Check every 10 seconds instead of sleeping once for 90s
        # This prevents the issue where CONNECTION_START_TIME gets reset while we're asleep
        check_interval = 10
        max_checks = MAX_CONNECTION_TIMEOUT // check_interval

        for i in range(int(max_checks) + 1):
            time.sleep(check_interval)

            # Check if we're still trying to connect
            if CONNECTION_START_TIME and (PAUSE_STATE or CONNECTING):
                elapsed = time.time() - CONNECTION_START_TIME

                # If we've exceeded the timeout, trigger recovery
                if elapsed > MAX_CONNECTION_TIMEOUT:
                    logging.warning(f"Connection monitor: timeout after {elapsed:.0f}s - forcing recovery")
                    force_connection_recovery("Connection timeout")
                    return
                elif i % 3 == 0:  # Log every 30 seconds
                    logging.info(f"Connection monitor: still connecting, elapsed: {elapsed:.0f}s/{MAX_CONNECTION_TIMEOUT}s")
            else:
                # Connection completed successfully, exit monitor
                logging.info("Connection monitor: connection completed, exiting monitor")
                return

    monitor_thread = threading.Thread(target=monitor_connection, daemon=True)
    monitor_thread.start()

def force_connection_recovery(reason="Unknown"):
    """Force recovery from stuck connection state - now uses smart recovery"""
    smart_connection_recovery(reason)

def new_report_exists(path):
    """
    Helper function for checking if the report is new relative to a given time stamp.
    """
    global LAST_INIT_REPORT_TIME, LAST_REPORT_TIME
    curr_report_mod_time = os.path.getmtime(path)
    if path == config.INITIAL_REPORT_P:
        last_report_ts = LAST_INIT_REPORT_TIME
        LAST_INIT_REPORT_TIME = curr_report_mod_time
    else:
        last_report_ts = LAST_REPORT_TIME
        LAST_REPORT_TIME = curr_report_mod_time
    return curr_report_mod_time > last_report_ts

async def switch_spec(direction='next', channel=None):
    """
    Handles "smart" spec switch. Resets data relevant to old connections and players. Can move either forward (default)
    or backwards (used by ?prev).
    """
    global STATE
    global IGNORE_IPS

    # ADD STATE VALIDATION
    if STATE is None:
        logging.error("Cannot switch spec: STATE is None")
        if channel:
            await channel.send("Bot state not available")
        return False

    IGNORE_IPS = []
    STATE.afk_list = []
    spec_ids = STATE.spec_ids if direction == 'next' else STATE.spec_ids[::-1]  # Reverse spec_list if going backwards.

    # ADD EMPTY LIST CHECK
    if not spec_ids:
        msg = "No players available to spectate"
        api.display_message(f"^7{msg}")
        logging.info(msg)
        if channel:
            await channel.send(msg)
        return False

    if STATE.current_player_id != STATE.bot_id:
        # ADD SAFETY CHECK FOR CURRENT PLAYER IN LIST
        try:
            current_index = spec_ids.index(STATE.current_player_id)
            next_id_index = current_index + 1
        except ValueError:
            # Current player not in spec list, start from beginning
            logging.warning(f"Current player {STATE.current_player_id} not in spec_ids, starting from first player")
            next_id_index = 0
        
        if next_id_index > len(spec_ids) - 1:
            next_id_index = 0
        follow_id = spec_ids[next_id_index]

        if follow_id == STATE.current_player_id:
            # Landed on the same id (list is length 1). No other players to spec.
            msg = "No other players to spectate."
            api.display_message(f"^7{msg}")
            logging.info(msg)
            if channel is not None:
                await channel.send(msg)
        else:
            display_player_name(follow_id)
            api.exec_command(f"follow {follow_id}")  # Follow this player.
            STATE.idle_counter = 0  # Reset idle strike flag since a followable non-bot id was found.
            STATE.current_player_id = follow_id  # Notify the state object of the new player we are spectating.
            STATE.afk_counter = 0

    return True

def spectate_player(follow_id):
    """Spectate player chosen by twich users based on their client id"""
    global IGNORE_IPS
    IGNORE_IPS = []
    STATE.afk_list = []
    if follow_id in STATE.spec_ids:
##        display_player_name(follow_id)
        api.exec_command(f"follow {follow_id}")  # Follow this player.
        STATE.idle_counter = 0  # Reset idle strike flag since a followable non-bot id was found.
        STATE.current_player_id = follow_id  # Notify the state object of the new player we are spectating.
        STATE.afk_counter = 0
        return f"Spectating {STATE.get_player_by_id(follow_id).n}"
    else:
        return f"Sorry, that player (id {follow_id}) is not available for spectating."


def display_player_name(follow_id):
    """
    Displays the player's name in the player-name custom cvar. Censor if in the list of blacklisted words.
    """
    follow_player = STATE.get_player_by_id(follow_id)
    if follow_player is not None:
        player_name = follow_player.n
        if check_for_blacklist_name(player_name):
            if STATE.show_name == True:
                logging.info(f"name is blacklisted: {player_name}")
                api.exec_command(f"set df_hud_drawSpecfollow 0")
                STATE.show_name = False
        else:
            if STATE.show_name == False:
                api.exec_command(f"set df_hud_drawSpecfollow 1")
                STATE.show_name = True


def check_for_blacklist_name(plyr_name):
    name = plyr_name.strip()
    blacklisted_words = config.get_list('blacklist_names')
    for word in blacklisted_words:
        if word in name.lower():
            return True
    return False


def get_svinfo_report(filename):
    """
    Handles parsed data of the server info report. Turns the parsed data into coherent objects.
    """
    global STATE

    with open(filename, "r") as svinfo_report_f:
        num_players = 0
        lines = svinfo_report_f.readlines()
        info, ip = parse_svinfo_report(lines)

        # Parse into objects
        if "Server Info" in info:
            server_info = info["Server Info"]
            server_info['physics'] = info['Info']['physics']
            server_info['curr_dfn'] = info['Info']['player']
            server_info['ip'] = ip
        else:
            time.sleep(5)
            return None, None, None
        players, spec_ids, nospec_ids, nopmids = [], [], [], []

    for header in info:
        try:
            match = re.match(r"^Client Info (\d+?)$", header)
            cli_id = match.group(1)
            player_data = info[header]

            players.append(Player(int(cli_id), player_data))
            num_players += 1
            if player_data['t'] != '3':  # Filter out spectators out of followable ids.
                if player_data['c1'] != 'nospec' and player_data['c1'] != 'nospecpm':
                    # Filter out nospec'd players out of followable ids
                    spec_ids.append(int(cli_id))
                else:
                    nospec_ids.append(int(cli_id))

                if player_data['c1'] == 'nospecpm':
                    nopmids.append(int(cli_id))

        except Exception:
            continue

    server_info['spec_ids'] = spec_ids
    server_info['nospec_ids'] = nospec_ids
    server_info['nopmids'] = nopmids
    return server_info, players, num_players


def parse_svinfo_report(lines):
    """
    Handles parsing of the server report files. Extracts only the necessary information, such as server and player data.
    """
    info = {}
    header = None

    title_r = r"= Report for (.*) \(*."
    header_r = r"^\*\*\* (.*)$"
    kv_r = r"^(.+?)\s+(.*)$"

    ip = None
    for line in [line for line in lines if line != ""]:

        # Check for ip
        if ip is None:
            try:
                # Extract server's ip
                ip = re.match(title_r, line).group(1)
            except Exception:
                pass

        # Check if line is a header
        try:
            header = re.match(header_r, line).group(1)

            # Create new dictionary for header
            if header not in info:
                info[header] = {}

            continue
        except Exception:
            pass

        # Don't parse any lines until we have a header
        if not header:
            continue

        # Check if line is a key-value pair
        try:
            match = re.match(kv_r, line)
            key = match.group(1)
            value = match.group(2)

            info[header][key] = value
        except Exception:
            pass

    return info, ip

def send_world_record_celebration(player_name=None, record_time=None):
    """
    Send a celebratory message for server/world record achievement with rate limiting
    """
    global LAST_WR_MESSAGE_TIME
    
    try:
        current_time = time.time()
        
        # Check if we're within cooldown period
        if current_time - LAST_WR_MESSAGE_TIME < WR_MESSAGE_COOLDOWN:
            time_remaining = int((WR_MESSAGE_COOLDOWN - (current_time - LAST_WR_MESSAGE_TIME)) / 60)
            logging.info(f"Server record message on cooldown. {time_remaining} minutes remaining.")
            return
        
        # Update last message time
        LAST_WR_MESSAGE_TIME = current_time
        
        # Get viewer count for some messages that use it
        viewer_count = get_twitch_viewer_count()
        if viewer_count < 1:
            viewer_count = "Several"  # Fallback text instead of number
        
        # Select random celebration message
        celebration_template = random.choice(WORLD_RECORD_MESSAGES)
        
        # Format message (some messages use {count}, others don't)
        if '{count}' in celebration_template:
            celebration_message = celebration_template.format(count=viewer_count)
        else:
            celebration_message = celebration_template
        
        # Send to game chat (NO PLAYER NAME OR TIME ADDED)
        logging.info(f"Sending server record celebration: {celebration_message}")
        api.exec_command(f"say {celebration_message}")
        
        # Also send a display message for extra emphasis (NO PLAYER NAME OR TIME)
        api.exec_command(f"cg_centertime 5;displaymessage 140 12 ^1SERVER RECORD BROKEN! ^7Epic performance witnessed!")
        
        # Send notification to Twitch chat via websocket (NO PLAYER NAME OR TIME)
        try:
            import console
            import json
            wr_notification = {
                'action': 'server_record_celebration',
                'message': f"SERVER RECORD BROKEN! The chat is going absolutely wild!"
            }
            console.WS_Q.put(json.dumps(wr_notification))
        except Exception as e:
            logging.error(f"Failed to send server record celebration to Twitch: {e}")
        
    except Exception as e:
        logging.error(f"Error sending server record celebration: {e}")

def handle_world_record_event(player_name=None, record_time=None):
    """
    Call this function when a server/world record is detected/broken
    """
    logging.info("Server record detected! Triggering celebration.")
    send_world_record_celebration(player_name, record_time)
    # Try to play sound, with error handling
    sound_file = 'worldrecord.wav'
    sound_path = f"D:\\Games\\defragtv\\defrag\\music\\common\\{sound_file}"
    if os.path.exists(sound_path):
        api.play_sound(sound_file)
    else:
        logging.warning(f"Sound file {sound_path} not found, skipping sound playback.")

def get_colored_player_names():
    """Fetch colored player names from defrag.racing API"""
    try:
        import requests
        current_ip = STATE.ip if STATE and hasattr(STATE, 'ip') else None
        if not current_ip:
            return {}
            
        # Add default port if not present
        api_ip = current_ip if ':' in current_ip else f"{current_ip}:27960"
        
        url = 'https://defrag.racing/servers/json'
        response = requests.get(url, timeout=5)
        servers_data = response.json()
        
        # Look for our server in active servers
        if 'active' in servers_data and api_ip in servers_data['active']:
            server_data = servers_data['active'][api_ip]
            colored_names = {}
            
            if 'players' in server_data:
                for player_id, player_data in server_data['players'].items():
                    if isinstance(player_data, dict) and 'name' in player_data:
                        # Map clean name to colored name
                        clean_name = remove_color_codes(player_data['name'])
                        colored_names[clean_name.lower()] = player_data['name']
            return colored_names
    except Exception as e:
        logging.error(f"Error fetching colored names: {e}")
    
    return {}

def remove_color_codes(text):
    """Remove Quake 3 color codes from text for comparison"""
    import re
    return re.sub(r'\^.', '', text)

def check_bot_team_status():
    """
    Periodic check to ensure bot is in spectator mode when it should be.
    Prevents bot from getting stuck in player mode.
    """
    global LAST_TEAM_CHECK_TIME, STATE
    
    current_time = time.time()
    
    # Only check every TEAM_CHECK_INTERVAL seconds
    if current_time - LAST_TEAM_CHECK_TIME < TEAM_CHECK_INTERVAL:
        return
        
    LAST_TEAM_CHECK_TIME = current_time
    
    # Skip check if in standby mode or during initialization
    if not STATE or not STATE_INITIALIZED or PAUSE_STATE:
        return
    
    # Get bot player object
    bot_player = STATE.get_player_by_id(STATE.bot_id)
    if not bot_player:
        logging.warning("TEAM DEBUG: Bot player not found during team check")
        return

    # Log current team status for debugging (only when change-based logging allows it)
    from config import LOG_ONLY_CHANGES
    team_snapshot = (int(bot_player.id) if bot_player and bot_player.id is not None else None, bot_player.t)
    global LAST_TEAM_SNAPSHOT
    should_log_team = False
    if not LOG_ONLY_CHANGES or LAST_TEAM_SNAPSHOT is None or LAST_TEAM_SNAPSHOT != team_snapshot:
        should_log_team = True

    if should_log_team:
        logging.info(f"TEAM DEBUG: Periodic check - Bot team: {bot_player.t}, Expected: 3 (spectator)")
        if LOG_ONLY_CHANGES:
            LAST_TEAM_SNAPSHOT = team_snapshot

    # Check if bot is in player mode when it should be spectating
    if bot_player.t != '3':  # '3' means spectator, anything else is player mode
        logging.warning(f"TEAM DEBUG: Bot detected in player mode (team={bot_player.t}) instead of spectator mode")
        logging.info("TEAM DEBUG: Forcing bot back to spectator mode...")

        # Force switch to spectator mode
        api.exec_command("team s")

        # Reset relevant counters since we're fixing a stuck state
        STATE.idle_counter = 0
        STATE.afk_counter = 0

        # Clear ignore IPs since this might help find active servers
        global IGNORE_IPS
        IGNORE_IPS = []

        logging.info("TEAM DEBUG: Bot forced back to spectator mode due to periodic check")

        # Verify the team switch worked
        time.sleep(2)
        api.exec_command("svinfo_report serverstate.txt", verbose=False)
        time.sleep(1)
        if new_report_exists(config.STATE_REPORT_P):
            _, updated_players, _ = get_svinfo_report(config.STATE_REPORT_P)
            updated_bot = [player for player in updated_players if player.id == STATE.bot_id]
            if updated_bot:
                logging.info(f"TEAM DEBUG: After retry - Bot team: {updated_bot[0].t}")
                if updated_bot[0].t != '3':
                    logging.error(f"TEAM DEBUG: CRITICAL - Bot still on team {updated_bot[0].t} after retry!")
    else:
        if should_log_team:
            logging.info(f"TEAM DEBUG: Bot correctly in spectator mode (team 3)")
            if len(STATE.spec_ids) == 0:
                logging.info("No spectatable players found after team switch - may trigger server switch")
