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
AFK_TIMEOUT = 1000 if config.DEVELOPMENT else 40  # Switch after afk detected x consecutive times.
#AFK_TIMEOUT = 5 if config.DEVELOPMENT else 5  # Switch after afk detected x consecutive times.
IDLE_TIMEOUT = 5 if config.DEVELOPMENT else 5  # Alone in server timeout.
INIT_TIMEOUT = 10  # Determines how many times to try the state initialization before giving up.
STANDBY_TIME = 1 if config.DEVELOPMENT else 15  # Time to wait before switching to next player.
VOTE_TALLY_TIME = 10  # Amount of time to wait while tallying votes
LAST_TEAM_CHECK_TIME = 0
TEAM_CHECK_INTERVAL = 30  # Check every 30 seconds
AFK_COUNTDOWN_ACTIVE = False
AFK_HELP_THREADS = []  # Track active help threads

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
    "^3SUBLIME! ^7That run had everything - ^2skill, precision, and HEART^7! ^4INCREDIBLE! ^6:P"
]

# Rate limiting for world records
LAST_WR_MESSAGE_TIME = 0
WR_MESSAGE_COOLDOWN = 60  # 1 minute

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
        token_url = f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
        token_response = requests.post(token_url)
        token = token_response.json()['access_token']
        stream_url = f"https://api.twitch.tv/helix/streams?user_login={'defraglive'}"
        headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
        response = requests.get(stream_url, headers=headers)
        stream_data = response.json()['data']
        return stream_data[0]['viewer_count'] if stream_data else 0
    except Exception as e:
        logging.error(f"Error getting Twitch viewer count: {e}")
        return 0


def send_auto_greeting():
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
            # Only reset current_player_id if it's invalid, don't always reset to bot_id
            # Convert player IDs to int for proper comparison
            player_ids = [int(p.id) for p in self.players]
            if self.current_player_id not in player_ids:
                self.current_player_id = self.bot_id
                logging.info(f"Reset current_player_id to bot_id due to invalid player")
            logging.info(f"Updated bot_id from stale value to {self.bot_id}")
        
        self.current_player = self.get_player_by_id(self.current_player_id)
        if self.bot_id in self.spec_ids:
            self.spec_ids.remove(self.bot_id)
        # remove afk players from speccable id list
        [self.spec_ids.remove(afk_id) for afk_id in self.afk_ids if afk_id in self.spec_ids]

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
        
        # Add auto greeting after custom connect message
        # Wait a bit to avoid message spam
        def delayed_greeting():
            time.sleep(3)  # 3 second delay
            send_auto_greeting()
        
        greeting_thread = threading.Thread(target=delayed_greeting, daemon=True)
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
                elif not VID_RESTARTING:
                    raise Exception("VidPaused")

                if new_report_exists(config.STATE_REPORT_P):
                    # Given that a new report exists, read this new data.
                    server_info, players, num_players = get_svinfo_report(config.STATE_REPORT_P)

                    if bool(server_info):  # New data is not empty and valid. Update the state object.
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
                if getattr(STATE, 'vote_active', False):
                    STATE.handle_vote()
        except Exception as e:
            if e.args[0] == 'Paused':
                logging.info("State paused.")
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
            time.sleep(1)


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
        time.sleep(3)
        for nospecid in STATE.nospec_ids:
            if nospecid in STATE.nopmids:
                # Send one-time message to nospecpm players
                api.exec_command('tell ' + str(nospecid) + ' ^7nospec active, ^3defraglive ^7cant spectate.')
                time.sleep(1)
                continue
            api.exec_command('tell ' + str(nospecid) + ' Detected nospec, to disable this feature write /color1 spec')
            time.sleep(1)
            api.exec_command('tell ' + str(nospecid) + ' To disable private notifications about nospec, set /color1 nospecpm')
        if STATE_INITIALIZED:
            # Schedule auto greeting message
            import threading
            def delayed_auto_greeting():
                import time
                time.sleep(5)  # Wait 5 seconds after connection
                send_auto_greeting()
            greeting_thread = threading.Thread(target=delayed_auto_greeting, daemon=True)
            greeting_thread.start()
    except:
        return False
    return True

    # if not mapdata_thread.is_alive():
    #     mapdata_thread.start()

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
    
    old_player_id = STATE.current_player_id  # Store for timeout cleanup
    
    # EXISTING DEBUG LOGGING
    logging.info(f"DEBUG: current_player_id={STATE.current_player_id}, bot_id={STATE.bot_id}")
    logging.info(f"DEBUG: spectating_self check: {STATE.current_player_id == STATE.bot_id}")
    if STATE.current_player:
        logging.info(f"DEBUG: current_player name: {STATE.current_player.n}")
    else:
        logging.info("DEBUG: current_player is None")
    
    logging.info(f"DEBUG: spec_ids={STATE.spec_ids}")
    logging.info(f"DEBUG: nospec_ids={STATE.nospec_ids}")
    logging.info(f"DEBUG: total players={len(STATE.players)}")
    for player in STATE.players:
        logging.info(f"DEBUG: Player {player.id}: {player.n}, team={player.t}, c1={player.c1}")
    
    # ADD THESE NEW DEBUG LINES HERE:
    logging.info(f"DEBUG: Looking for player with ID {STATE.current_player_id}")
    logging.info(f"DEBUG: get_player_by_id result: {STATE.get_player_by_id(STATE.current_player_id)}")
    
    # Wrap the team check in try-catch to prevent crashing the main loop
    try:
        check_bot_team_status()
    except Exception as e:
        logging.error(f"Error in team status check: {e}")
        # Continue with normal validation even if team check fails
    
    if STATE.get_player_by_id(STATE.bot_id) is None:
        spectating_self = False
    else:
        # Current player spectated is our bot, and thus idle.
        spectating_self = STATE.curr_dfn == STATE.get_player_by_id(STATE.bot_id).dfn \
                      or STATE.current_player_id == STATE.bot_id

    # Current player spectated has turned on the no-spec system
    spectating_nospec = STATE.current_player_id not in STATE.spec_ids and STATE.current_player_id != STATE.bot_id

    # Get the AFK timeout for current player (could be extended)
    current_afk_timeout = STATE.get_afk_timeout_for_player(STATE.current_player_id)

    # The player that we are spectating has been AFK for their custom limit
    spectating_afk = STATE.afk_counter >= current_afk_timeout

    # AFK player pre-processing
    if spectating_afk:
        try:
            STATE.spec_ids.remove(STATE.current_player_id)  # Remove afk player from list of spec-able players
            # Add them to the afk list
            STATE.afk_ids.append(STATE.current_player_id) if STATE.current_player_id not in STATE.afk_ids else None
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
        follow_id = random.choice(STATE.spec_ids) if STATE.spec_ids != [] else STATE.bot_id  # Find someone else to spec

        if follow_id != STATE.bot_id:  # Found someone successfully, follow this person
            # Reset timeout for old player back to default when switching to different player
            if old_player_id != follow_id and old_player_id and str(old_player_id) in STATE.player_afk_timeouts:
                del STATE.player_afk_timeouts[str(old_player_id)]
                logging.info(f"Reset AFK timeout for player {old_player_id} back to default (player switch)")

            if spectating_nospec:
                if not PAUSE_STATE and not spectating_self:
                    # Determine WHY player is not specable for better error message
                    target_player = STATE.get_player_by_id(STATE.current_player_id)
                    if target_player:
                        if target_player.t == '3':  # Player is a spectator
                            logging.info('Free spectator detected. Switching...')
                            api.display_message("^7Can't spec free spectators. Switching.")
                        elif target_player.c1 in ['nospec', 'nospecpm']:  # Actual nospec
                            logging.info('Nospec detected. Switching...')
                            api.display_message("^7Nospec detected. Switching.")
                        else:  # Other reason (shouldn't happen but fallback)
                            logging.info('Player not specable. Switching...')
                            api.display_message("^7Player unavailable. Switching.")
                    else:
                        # Fallback if player object not found
                        logging.info('Player not specable. Switching...')
                        api.display_message("^7Player unavailable. Switching.")

            display_player_name(follow_id)
            api.exec_command(f"follow {follow_id}")
            STATE.current_player_id = int(follow_id)
            STATE.current_player = STATE.get_player_by_id(int(follow_id))
            STATE.idle_counter = 0  # Reset idle strike flag since a followable non-bot id was found.
            STATE.afk_counter = 0
            logging.info(f"Successfully switched to player {follow_id}")
            return  # CRITICAL: Exit validation after successful switch

        else:  # Only found ourselves to spec.
            if STATE.current_player_id != STATE.bot_id:  # Stop spectating player, go to free spec mode instead.
                # Reset timeout when switching to bot
                if str(STATE.current_player_id) in STATE.player_afk_timeouts:
                    del STATE.player_afk_timeouts[str(STATE.current_player_id)]
                    logging.info(f"Reset AFK timeout for player {STATE.current_player_id} back to default (switching to bot)")
                
                api.exec_command(f"follow {follow_id}")
                STATE.current_player_id = STATE.bot_id
            else:  # Was already spectating self. This is an idle strike
                STATE.idle_counter += 1
                logging.info(f"Not spectating. Strike {STATE.idle_counter}/{IDLE_TIMEOUT}")
                if not PAUSE_STATE:
                    api.display_message(f"^3Strike {STATE.idle_counter}/{IDLE_TIMEOUT}", time=1)

            if STATE.idle_counter >= IDLE_TIMEOUT or spectating_afk:
                # There's been no one on the server for a while or only afks. Switch servers.
                IGNORE_IPS.append(STATE.ip) if STATE.ip not in IGNORE_IPS and STATE.ip != "" else None
                new_ip = servers.get_next_active_server(IGNORE_IPS)
                print("new_ip: " + str(new_ip))

                api.exec_command("say ^1AFK/Nospec ^7on all available players has been detected. ^3Farewell.")

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
        inputs = STATE.get_inputs()
        if inputs == '':
            # Empty key presses. This is an AFK strike.
            STATE.afk_counter += 1
            
            # Show notifications every 10 strikes starting from strike 15, but use custom timeout
            if STATE.afk_counter >= 15 and STATE.afk_counter % 10 == 5:  # Every 10 strikes after 15: 15, 25, 35...
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
            
            # Show help notification every 10 strikes starting from strike 20 (in between main notifications)
            elif STATE.afk_counter >= 20 and STATE.afk_counter % 10 == 0:  # Every 10 strikes at 20, 30, 40...
                remaining_time = (current_afk_timeout - STATE.afk_counter) * 2
                if remaining_time > 0:
                    AFK_COUNTDOWN_ACTIVE = True  # ADD THIS LINE
                    logging.info(f"AFK help notification. Strike {STATE.afk_counter}/{current_afk_timeout}")
                    
                    # Send first help message to in-game - BUT CHECK IF CONNECTING
                    if not PAUSE_STATE and not CONNECTING:
                        api.display_message(f"Use ^3?afk reset ^7to restart afk counter", time=2)
                    
                    # Send second help message after 3 seconds - WITH CANCELLATION CHECK
                    def send_second_help():
                        import time
                        time.sleep(3)
                        # CHECK IF COUNTDOWN IS STILL ACTIVE BEFORE SENDING MESSAGE
                        if AFK_COUNTDOWN_ACTIVE and not PAUSE_STATE and not CONNECTING:
                            api.display_message(f"Use ^3?afk extend ^7to extend by 5min", time=2)
                        else:
                            logging.info("AFK help message cancelled due to server connection/pause")
                    
                    import threading
                    help_thread = threading.Thread(target=send_second_help)
                    help_thread.daemon = True
                    help_thread.start()
                    
                    # Track the thread so we can manage it
                    AFK_HELP_THREADS.append(help_thread)
                    
                    # Also send help to Twitch chat
                    try:
                        import console
                        import json
                        help_msg = {
                            'action': 'afk_help',
                            'message': f"AFK Strike {STATE.afk_counter}/{current_afk_timeout} - Use ?afk reset to restart or ?afk extend for +5min"
                        }
                        console.WS_Q.put(json.dumps(help_msg))
                    except Exception as e:
                        logging.error(f"Failed to send AFK help notification to Twitch: {e}")
                        
        else:
            # Activity detected, reset AFK strike counter and empty AFK list + ip blacklist
            if STATE.afk_counter >= 15:
                api.display_message("Activity detected. ^3AFK counter aborted.")
                logging.info("Activity detected. AFK counter aborted.")

            STATE.afk_counter = 0
            STATE.afk_ids = []
            IGNORE_IPS = []
            # CANCEL ANY ACTIVE AFK COUNTDOWNS
            AFK_COUNTDOWN_ACTIVE = False
            AFK_HELP_THREADS.clear()
            # DO NOT reset timeout when player becomes active - keep extended timeout until player switch
            # The timeout will only be reset when switching to a different player (handled above)

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

    # ABORT ALL AFK COUNTDOWNS AND HELP MESSAGES IMMEDIATELY
    AFK_COUNTDOWN_ACTIVE = False  # This will stop any running countdown threads
    
    # Cancel any pending AFK help messages
    for thread in AFK_HELP_THREADS:
        if thread.is_alive():
            logging.info("Cancelling AFK help thread due to server connection")
            # Threads will check AFK_COUNTDOWN_ACTIVE flag and exit
    AFK_HELP_THREADS.clear()

    STATE_INITIALIZED = False
    logging.info(f"Connecting to {ip}...")
    PAUSE_STATE = True
    CONNECTING = True
    
    if STATE:  # Check if STATE exists before accessing it
        STATE.idle_counter = 0
        STATE.afk_counter = 0
        STATE.afk_ids = []
    
    if caller is not None:
        if STATE:
            STATE.connect_msg = f"^7Brought by ^3{caller}"
        IGNORE_IPS = []

    RECONNECTED_CHECK = True
    CURRENT_IP = ip

    api.exec_command("connect " + ip, verbose=False)


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

    IGNORE_IPS = []
    STATE.afk_list = []
    spec_ids = STATE.spec_ids if direction == 'next' else STATE.spec_ids[::-1]  # Reverse spec_list if going backwards.

    if STATE.current_player_id != STATE.bot_id:
        # Determine the next followable id. If current id is at the last index, wrap to the beginning of the list.
        next_id_index = spec_ids.index(STATE.current_player_id) + 1
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

        except:
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
            except:
                pass

        # Check if line is a header
        try:
            header = re.match(header_r, line).group(1)

            # Create new dictionary for header
            if header not in info:
                info[header] = {}

            continue
        except:
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
        except:
            pass

    return info, ip

def send_world_record_celebration(player_name=None, record_time=None):
    """
    Send a celebratory message for server/world record achievement with rate limiting
    """
    global LAST_WR_MESSAGE_TIME
    
    try:
        current_time = time.time()  # Now this works correctly
        
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
        
        # Add player name and time if provided
        if player_name and record_time:
            celebration_message = f"{celebration_message} ^3{player_name}^7 with ^2{record_time}^7!"
        
        # Send to game chat
        logging.info(f"Sending server record celebration: {celebration_message}")
        api.exec_command(f"say {celebration_message}")
        
        # Also send a display message for extra emphasis
        api.exec_command(f"cg_centertime 5;displaymessage 140 12 ^1SERVER RECORD! ^7{player_name or 'Someone'} with ^2{record_time or 'an epic time'}^7!")
        
        # Send notification to Twitch chat via websocket
        try:
            import console
            import json
            wr_notification = {
                'action': 'server_record_celebration',
                'message': f"SERVER RECORD BROKEN by {player_name or 'someone'} with {record_time or 'an epic time'}! The chat is going wild!"
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
    logging.info(f"Server record detected! Triggering celebration for {player_name or 'unknown player'} with time {record_time or 'unknown time'}.")
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
        logging.warning("Bot player not found during team check")
        return
    
    # Check if bot is in player mode when it should be spectating
    if bot_player.t != '3':  # '3' means spectator, anything else is player mode
        logging.warning(f"Bot detected in player mode (team={bot_player.t}) instead of spectator mode")
        logging.info("Forcing bot back to spectator mode...")
        
        # Force switch to spectator mode
        api.exec_command("team s")
        
        # Reset relevant counters since we're fixing a stuck state
        STATE.idle_counter = 0
        STATE.afk_counter = 0
        
        # Clear ignore IPs since this might help find active servers
        global IGNORE_IPS
        IGNORE_IPS = []
        
        logging.info("Bot forced back to spectator mode due to periodic check")
        
        # If we're alone on server after switching to spec, trigger server switching logic
        if len(STATE.spec_ids) == 0:
            logging.info("No spectatable players found after team switch - may trigger server switch")
