"""
This file has the following purposes:
1. Reads the console in real time.
2. Listens for commands and starts the proper pipeline when a command is activated.
3. Formats chat, server prints, and server notifications nicely for the twitch extension.
"""
import os
import time
import re
import queue
import json
import api
from hashlib import blake2b
import logging
import twitch_commands

import dfcommands as cmd
import filters
import serverstate
import servers

LOG = []
CONSOLE_DISPLAY = []
FILTERS = ["R_AddMD3Surfaces"]
WS_Q = queue.Queue()
STOP_CONSOLE = False

ERROR_FILTERS = {
    "ERROR: CL_ParseServerMessage:": "RECONNECT",
    "ERROR: Unhandled exception caught": "RECONNECT",
    "Signal caught (11)": "RECONNECT",
    "Incorrect challenge, please reconnect": "RECONNECT"
    #"ERROR: CM_LoadMap:": "DIFFERENT_IP"
}


def read_tail(thefile):
        '''
        Generator function that yields new lines in a file
        '''

        global STOP_CONSOLE

        # seek the end of the file
        thefile.seek(0, os.SEEK_END)
        
        # start infinite loop
        while not STOP_CONSOLE:
            # read last line of file
            line = thefile.readline()

            # sleep if file hasn't been updated
            if not line:
                time.sleep(0.25)
                continue

            yield line


def read(file_path: str):
    """
    Reads the console log file every second and sends the console lines for processing
    :param file_path: Full file path to the qconsole.log file
    :return: None
    """

    global LOG
    global CONSOLE_DISPLAY
    global FILTERS
    global STOP_CONSOLE

    while not os.path.isfile(file_path):
        time.sleep(1)

    STOP_CONSOLE = False
    with open(file_path, 'r') as log:
        new_lines = read_tail(log)

        for line in new_lines:
            for filter in FILTERS:
                if filter in line:
                    continue

            line_data = process_line(line)

            # Filter
            line_data = filters.filter_line_data(line_data)

            LOG.append(line_data)

            # Cut log to size
            if(len(LOG) > 5000):
                LOG = LOG[1000:]

            # if line_data.pop("command") is not None:
            if 'command' in line_data and line_data['command'] is not None:
                command = line_data['command']
                handle_command = getattr(cmd, f"handle_{command}")
                try:
                    handle_command(line_data)
                except Exception as e:
                    logging.info(f"Error occurred for in-game command {command}: {e}")

            if line_data["type"] in ["PRINT", 
                                     "SAY", 
                                     "ANNOUNCE", 
                                     "RENAME", 
                                     "CONNECTED", 
                                     "DISCONNECTED", 
                                     "ENTEREDGAME", 
                                     "JOINEDSPEC",
                                     "REACHEDFINISH",
                                     "YOURRANK"]:
                CONSOLE_DISPLAY.append(line_data)
                WS_Q.put(json.dumps({'action': 'message', 'message': line_data}))


def message_to_id(msg):
    return blake2b(bytes(msg, "utf-8"), digest_size=8, salt=os.urandom(blake2b.SALT_SIZE)).hexdigest()

# Not the most accurate way, but it works for most players
# The only exception is when a player has (:) in their name
def is_server_msg(line, msg):
    data = line[:line.index(msg)]

    return not ':' in data

def process_line(line):
    """
    Processes a console line into a more useful format. Extracts type (say, announcement, print) as well as author
    and content if applicable.
    :param line: Console line to be processed
    :return: Data dictionary containing useful data about the line
    """

    global ERROR_FILTERS

    line = line.strip()

    line_data = {
        "id": message_to_id(f"{time.time()}_MISC"),
        "type": "MISC", 
        "command": None, 
        "author": None, 
        "content": line, 
        "timestamp": time.time()
    }

    errors = ['ERROR: Unhandled exception cought'] # you can add more errors like this: ['error1', 'error2', 'error3']


    # SERVERCOMMAND

    try:
        # Don't log if it's a report
        if "report written to system/reports/initialstate.txt" in line or "report written to system/reports/serverstate.txt" in line:
            pass
        else:
            logging.info(f"[Q3] {line}")

        if line in {"VoteVote passed.", "RE_Shutdown( 0 )"}:
            if not serverstate.PAUSE_STATE:
                serverstate.PAUSE_STATE = True
                logging.info("Game is loading. Pausing state.")

        if line in ERROR_FILTERS:
            if ERROR_FILTERS[line] == "RECONNECT":
                logging.info("Reconnecting to server...")
                api.exec_command("connect " + serverstate.STATE.ip)
            elif ERROR_FILTERS[line] == "DIFFERENT_IP":
                logging.info("Server IP changed. Reconnecting...")
                api.exec_command("connect " + servers.get_next_active_server([serverstate.STATE.ip]))

        if 'broke the server record with' in line and is_server_msg(line, 'broke the server record with'):
            """ 
                Maybe we can also add a display message with the player name and/or the record 
                #playerName = line[:line.index(' broke the server record with')]
                #playerRecord = line[line.index(' broke the server record with') + len(' broke the server record with'):]
                #api.display_message("{playerName} broke the record with {playerRecord}")
            """
            api.play_sound("worldrecord.wav")

        if 'called a vote:' in line and is_server_msg(line, 'called a vote:'):
            logging.info("Vote detected.")
            if serverstate.STATE.num_players == 2:  # only bot and 1 other player in game, always f1
                logging.info("1 other player in server, voting yes.")
                api.exec_command("vote yes")
                api.exec_command("say ^7Vote detected. Voted ^3f1^7.")
            else:
                logging.info("Multiple people in server, initiating vote tally.")
                serverstate.STATE.init_vote()
                api.exec_command("say ^7Vote detected. Should I vote yes or no? Send ^3?^7f1 for yes and ^3?^7f2 for no.")


        if line.startswith('Com_TouchMemory: 0 msec'):
            serverstate.PAUSE_STATE = False

        if line.startswith('Not recording a demo.') or line.startswith("report written to system/reports/initialstate.txt"):
            if serverstate.CONNECTING:
                time.sleep(1)
                serverstate.CONNECTING = False
            elif serverstate.VID_RESTARTING:
                time.sleep(1)
                logging.info("vid_restart done.")
                serverstate.PAUSE_STATE = False
                serverstate.VID_RESTARTING = False
            elif serverstate.PAUSE_STATE:
                time.sleep(1)
                serverstate.PAUSE_STATE = False
                logging.info("Game loaded. Continuing state.")
                serverstate.STATE.say_connect_msg()

            # for player in serverstate.players:
            #     api.exec_command('tell ' + str(player.id) + ' Hey, "nospec" is on and your Twitch fans can\'t spectate you. Consider turning it off for them to fully enjoy your gameplay.')
            #     api.exec_command('tell ' + str(player.id) + ' If you would like to turn off "nospec" feature off please write this command /color1 spec')

        # sc_r = r"^\^5serverCommand:\s*(\d+?)\s*:\s*(.+?)$"
        # match = re.match(sc_r, line)
        #
        # sv_command_id = match.group(1)
        # sv_command = match.group(2)

        def parse_chat_message(command):
            # CHAT MESSAGE (BY PLAYER)

            # chat_message_r = r"^chat\s*\"[\x19]*\[*(.*?)[\x19]*?\]*?\x19:\s*(.*?)\".*?$" #/developer 1
            chat_message_r = r"(.*)\^7: \^\d(.*)"
            match = re.match(chat_message_r, command)

            chat_name = match.group(1)
            chat_message = match.group(2)

            line_data["id"] = message_to_id(f"SAY_{chat_name}_{chat_message}")
            line_data["type"] = "SAY"
            line_data["author"] = chat_name
            line_data["content"] = chat_message
            line_data["command"] = cmd.scan_for_command(chat_message)

        def parse_chat_announce(command):
            # CHAT ANNOUNCEMENT
            chat_announce_r = r"^chat\s*\"(.*?)\".*?$"
            match = re.match(chat_announce_r, command)

            chat_announcement = match.group(1)

            line_data["id"] = message_to_id(f"ANN_{chat_announcement}")
            line_data["type"] = "ANNOUNCE"
            line_data["author"] = None
            line_data["content"] = chat_announcement

        def parse_print(command):
            # PRINT
            print_r = r"^print\s*\"(.*?)$" # Prints have their ending quotation mark on the next line, very strange
            match = re.match(print_r, command)

            print_message = match.group(1)

            line_data["id"] = message_to_id(f"PRINT_{print_message}")
            line_data["type"] = "PRINT"
            line_data["author"] = None
            line_data["content"] = print_message

        def parse_scores(command):
            # SCORES
            scores_r = r"^scores\s+(.*?)$"
            match = re.match(scores_r, command)

            scores = match.group(1)

            line_data["id"] = message_to_id(f"SCORES_{scores}")
            line_data["type"] = "SCORES"
            line_data["author"] = None
            line_data["content"] = scores

        def parse_rename(command):
            if ' renamed to ' in command:
                line_data["id"] = message_to_id(f"RENAME_{command}")
                line_data["type"] = "RENAME"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_connected(command):
            if ' ^7connected' in command:
                line_data["id"] = message_to_id(f"CONNECTED_{command}")
                line_data["type"] = "CONNECTED"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_disconnected(command):
            if ' disconnected' in command:
                line_data["id"] = message_to_id(f"DISCONNECTED_{command}")
                line_data["type"] = "DISCONNECTED"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_entered_game(command):
            if ' entered the game.' in command:
                line_data["id"] = message_to_id(f"ENTEREDGAME_{command}")
                line_data["type"] = "ENTEREDGAME"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_joined_spec(command):
            if ' joined the spectators.' in command:
                line_data["id"] = message_to_id(f"JOINEDSPEC_{command}")
                line_data["type"] = "JOINEDSPEC"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_reached_finish(command):
            if ' reached the finish line in ' in command:
                line_data["id"] = message_to_id(f"REACHEDFINISH_{command}")
                line_data["type"] = "REACHEDFINISH"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_your_rank(command):
            if ' you are now rank ' in command:
                line_data["id"] = message_to_id(f"YOURRANK_{command}")
                line_data["type"] = "YOURRANK"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        # TODO: '... broke the server record ...'
        # TODO: '!top results?'
        # logging.info(f'LINE: {line}')

        for fun in [
                    parse_chat_message, 
                    parse_chat_announce, 
                    parse_print, 
                    parse_scores, 
                    parse_rename, 
                    parse_connected,
                    parse_disconnected,
                    parse_entered_game,
                    parse_joined_spec,
                    parse_reached_finish,
                    parse_your_rank]:
            try:
                # fun(sv_command)
                fun(line)
                break
            except:
                continue
    except:
        return line_data

    # logging.info(line_data)
    return line_data


# HELPER
def handle_fuzzy(r, fuzzy):
    if not r:
        return r

    if fuzzy:
        return "^.*?" + re.escape(r) + ".*?$"
    else:
        return r


# HELPER
def check_line(line_obj, end_type, end_author, end_content, end_content_fuzzy):
    if end_type and end_type != line_obj["type"]:
        return False

    if end_author and end_author != line_obj["author"]:
        return False

    if end_content:
        end_content = handle_fuzzy(end_content, end_content_fuzzy)

        try:
            if not re.match(end_content, line_obj["content"]):
                return False
        except:
            return False

    return True


def get_log_line(within, end_type=None, end_author=None, end_content=None, end_content_fuzzy=True):
    global LOG

    ts = time.time()

    slice = [line for line in LOG if ts - line["timestamp"] < within]

    for line in slice:
        if check_line(line, end_type, end_author, end_content, end_content_fuzzy):
            return line

    return None


def wait_log(start_ts=0, end_type=None, end_author=None, end_content=None, end_content_fuzzy=True, delay=0.5, abort_after=20.0):
    logging.info("WAIT FOR LOG PARSED", start_ts, end_type, end_author, end_content, end_content_fuzzy, delay)

    exec_start_ts = time.time()

    global LOG

    length = len(LOG)

    # Slice log, check lines, etc
    # Check initial slice
    slice = [line for line in LOG if line["timestamp"] > start_ts]

    logging.info("INITIAL", slice)

    for line in slice:
        if check_line(line, end_type, end_author, end_content, end_content_fuzzy):
            logging.info("FOUND", line)
            return line

    while True:
        # Abort if we have timed out
        if time.time() - exec_start_ts > abort_after:
            raise TimeoutError

        length_new = len(LOG)

        if length_new == length:
            time.sleep(delay)
            continue

        slice = LOG[length : length_new]

        logging.info("MORE", slice)

        for line in slice:
            if check_line(line, end_type, end_author, end_content, end_content_fuzzy):
                logging.info("FOUND", line)
                return line

        time.sleep(delay)
