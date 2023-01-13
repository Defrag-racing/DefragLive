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
import threading
import json
from hashlib import md5
# import mapdata
from websocket_console import notify_serverstate_change


# Configurable variables, Strike = 2seconds
MESSAGE_REPEATS = 1  # How many times to spam info messages. 0 for no messages.
AFK_TIMEOUT = 10 if config.DEVELOPMENT else 40  # Switch after afk detected x consecutive times.
IDLE_TIMEOUT = 999999 if config.DEVELOPMENT else 5  # Alone in server timeout.
INIT_TIMEOUT = 10  # Determines how many times to try the state initialization before giving up.
STANDBY_TIME = 15  # Amount of time to standby in minutes
VOTE_TALLY_TIME = 5  # Amount of time to wait while tallying votes


STATE = None
PAUSE_STATE = False
IGNORE_IPS = []
CONNECTING = False
VID_RESTARTING = False
STATE_INITIALIZED = False
LAST_REPORT_TIME = time.time()
LAST_INIT_REPORT_TIME = time.time()

# mapdata_thread = threading.Thread(target=mapdata.mapdataHook, daemon=True)


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

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)

    def update_info(self, server_info):
        """Helper function for resetting the class's properties on state referesh"""
        for key in server_info:
            setattr(self, key.replace('sv_', ''), server_info[key])
        self.current_player = self.get_player_by_id(self.current_player_id)
        if self.bot_id in self.spec_ids:
            self.spec_ids.remove(self.bot_id)
        # remove afk players from speccable id list
        [self.spec_ids.remove(afk_id) for afk_id in self.afk_ids if afk_id in self.spec_ids]

    def get_player_by_id(self, c_id):
        """Helper function for easily retrieving a player object from a client id number"""
        id_player = [player for player in self.players if player.id == c_id]
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
        self.nospec = self.c1 == 'nospec'


def start():
    """
    The main gateway for fetching the server state through /svinfo_report. It runs through a loop indefinitely and
    attempts to extract new data only if state is not paused through the PAUSE_STATE flag.
    """
    global STATE
    global PAUSE_STATE
    global VID_RESTARTING

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
                            notify_serverstate_change() # Notify all websocket clients about new serverstate
                        prev_state = curr_state
                        prev_state_hash = curr_state_hash
                        display_player_name(STATE.current_player_id)
                if getattr(STATE, 'vote_active', False):
                    STATE.handle_vote()
        except Exception as e:
            if e.args[0] == 'Paused':
                logging.info("State paused.")
                pass
            elif e.args[0] == 'VidPaused':
                logging.info("Vid paused.")
            else:
                prev_state, prev_state_hash, curr_state = None, None, None
                initialize_state()  # Handle the first state fetch. Some extra processing needs to be done this time.
                logging.info(f"State failed: {e}")
            time.sleep(1)


def initialize_state():
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

    try:
        # Create a secret code. Only "secret" for one use.
        secret = ''.join(random.choice('0123456789ABCDEF') for i in range(16))
        server_info, bot_player, timeout_flag = None, [], 0

        init_counter = 0
        while server_info is None or bot_player == []:  # Continue running this block until valid data and bot id found
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
        STATE.num_players = num_players
        STATE_INITIALIZED = True
        logging.info("State Initialized.")

        time.sleep(3)
        for nospecid in STATE.nospec_ids:
            api.exec_command('tell ' + str(nospecid) + ' Hey, "nospec" is on and your Twitch fans can\'t spectate you. Consider turning it off for them to enjoy your gameplay.')
            time.sleep(1)
            api.exec_command('tell ' + str(nospecid) + ' If you would like to turn off "nospec" feature off please write this command /color1 spec')
            time.sleep(1)
    except:
        return False

    # if not mapdata_thread.is_alive():
    #     mapdata_thread.start()

    return True


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

    if STATE.get_player_by_id(STATE.bot_id) is None:
        spectating_self = False

    else:
    # Current player spectated is our bot, and thus idle.
        spectating_self = STATE.curr_dfn == STATE.get_player_by_id(STATE.bot_id).dfn \
                      or STATE.current_player_id == STATE.bot_id

    # Current player spectated has turned on the no-spec system
    spectating_nospec = STATE.current_player_id not in STATE.spec_ids and STATE.current_player_id != STATE.bot_id

    # The player that we are spectating has been AFK for our set limit of AFK strikes
    spectating_afk = STATE.afk_counter >= AFK_TIMEOUT

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
        except ValueError:
            pass

    # Next player choice logic
    if spectating_self or spectating_nospec or spectating_afk:
        follow_id = random.choice(STATE.spec_ids) if STATE.spec_ids != [] else STATE.bot_id  # Find someone else to spec

        if follow_id != STATE.bot_id:  # Found someone successfully, follow this person
            if spectating_nospec:
                if not PAUSE_STATE and not spectating_self:
                    print("spectating_nospec: " + str(spectating_nospec))
                    print("state.spec_ids: " + str(json.dumps(STATE.spec_ids)))
                    print("state.current_player_id: " + str(STATE.current_player_id))
                    print("state.bot_id: " + str(STATE.bot_id))
                    print("follow_id: " + str(follow_id))

                    logging.info('Nospec detected. Switching...')
                    api.display_message("^7Nospec detected. Switching to the next player.")

            display_player_name(follow_id)
            api.exec_command(f"follow {follow_id}")

            api.exec_command("say It appears that the player has been inactive for over a minute, so I will be moving on to the next available player.")

            STATE.idle_counter = 0  # Reset idle counter

        else:  # Only found ourselves to spec.
            if STATE.current_player_id != STATE.bot_id:  # Stop spectating player, go to free spec mode instead.
                api.exec_command(f"follow {follow_id}")
                STATE.current_player_id = STATE.bot_id
            else:  # Was already spectating self. This is an idle strike
                STATE.idle_counter += 1
                logging.info(f"Not spectating. Strike {STATE.idle_counter}/{IDLE_TIMEOUT}")
                if not PAUSE_STATE:
                    api.display_message(f"^3Strike {STATE.idle_counter}/{IDLE_TIMEOUT}", time=1)

            if STATE.idle_counter >= IDLE_TIMEOUT or spectating_afk:
                # There's been no one on the server for a while or only afks. Switch servers.

                # Ignore this ip until a good server is found
                IGNORE_IPS.append(STATE.ip) if STATE.ip not in IGNORE_IPS and STATE.ip != "" else None
                new_ip = servers.get_next_active_server(IGNORE_IPS)
                print("new_ip: " + str(new_ip))

                api.exec_command("say It's been fun, but the activity has decreased and audience interest is waning. Thank you for your time and farewell.")

                if bool(new_ip):
                    connect(new_ip)
                    return
                else:  # No ip left to connect to, go on standby mode.
                    api.exec_command("map st1")
                    STANDBY_START_T = time.time()
                    msg_switch_t = 15  # time in seconds to switch between the two standby messages
                    while IGNORE_IPS != [] and (time.time() - STANDBY_START_T) < 60 * STANDBY_TIME:
                        api.exec_command("team s")

                        api.exec_command("say ^3No active servers. On standby mode.")
                        #  api.display_message("No active servers. On standby mode.", time=msg_switch_t + 1)
                        time.sleep(msg_switch_t)
                        api.exec_command("say Use ^3?^7connect ^3ip^7 or ^3?^7restart to continue the bot^3.")
                        #  api.display_message("Use ^3?^7connect ^3ip^7 or ^3?^7restart to continue the bot^3.", time=msg_switch_t)
                        time.sleep(msg_switch_t)
                    IGNORE_IPS = []  # continue after standby time elapsed or viewer has performed an action
        STATE.current_player_id = follow_id  # Spectating someone.
        STATE.current_player = STATE.get_player_by_id(follow_id)

    else:  # AFK detection
        inputs = STATE.get_inputs()
        if inputs == '': # Empty key presses. This is an AFK strike.
            STATE.afk_counter += 1
            if STATE.afk_counter >= 15 and STATE.afk_counter % 5 == 0:
                logging.info(f"AFK detected. Strike {STATE.afk_counter}/{AFK_TIMEOUT}")
                api.display_message(f" AFK detected. Switching in {(int(AFK_TIMEOUT-STATE.afk_counter)*2)} seconds.", time=5)
        else:
            # Activity detected, reset AFK strike counter and empty AFK list + ip blacklist
            if STATE.afk_counter >= 15:
                api.display_message("Activity detected. ^3AFK counter aborted.")
                logging.info("Activity detected. AFK counter aborted.")

            STATE.afk_counter = 0
            STATE.afk_ids = []
            IGNORE_IPS = []


def connect(ip, caller=None):
    """
    Handles connection to a server and re-attempts if connection is not resolved.
    """
    global PAUSE_STATE
    global STATE_INITIALIZED
    global CONNECTING
    global IGNORE_IPS

    STATE_INITIALIZED = False
    logging.info(f"Connecting to {ip}...")
    PAUSE_STATE = True
    CONNECTING = True
    STATE.idle_counter = 0
    STATE.afk_counter = 0
    STATE.afk_ids = []
    if caller is not None:
        STATE.connect_msg = f"^7Brought by ^3{caller}"
        IGNORE_IPS = []

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

        if follow_id == STATE.current_player_id: # Landed on the same id (list is length 1). No other players to spec.
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
        players, spec_ids, nospec_ids = [], [], []

    for header in info:
        try:
            match = re.match(r"^Client Info (\d+?)$", header)
            cli_id = match.group(1)
            player_data = info[header]

            players.append(Player(cli_id, player_data))
            num_players += 1
            if player_data['t'] != '3':  # Filter out spectators out of followable ids.
                if player_data['c1'] != 'nospec':  # Filter out nospec'd players out of followable ids
                    spec_ids.append(cli_id)
                else:
                    nospec_ids.append(cli_id)
        except:
            continue

    server_info['spec_ids'] = spec_ids
    server_info['nospec_ids'] = nospec_ids
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
                ip = re.match(title_r, line).group(1)  # Extract server's ip
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
