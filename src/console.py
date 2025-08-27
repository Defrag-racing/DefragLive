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
import threading
from hashlib import blake2b
import logging
import threading
import dfcommands as cmd
import filters
import serverstate
import servers

LOG = []
CONSOLE_DISPLAY = []
FILTERS = ["R_AddMD3Surfaces"]
WS_Q = queue.Queue()
STOP_CONSOLE = False
PREVIOUS_LINE = ''
LAST_ERROR_TIME = None
PAUSE_STATE_START_TIME = None  # Add this global variable
DELAYED_MESSAGE_QUEUE = []

ERROR_FILTERS = {
    "ERROR: CL_ParseServerMessage:": "RECONNECT",
    "Exception Code: ACCESS_VIOLATION": "RECONNECT",
    "Signal caught (11)": "RECONNECT",
    "Incorrect challenge, please reconnect": "RECONNECT",
    "ERROR: CL_ParseServerMessage: read past end of server message": "RECONNECT",
    "^0^7D^6e^7Frag^6.^7LIVE^0/^7 was kicked": "RECONNECT",
    "Server connection timed out": "RECONNECT"
}


def check_pause_timeout():
    """
    Check if state has been paused for too long and trigger reconnect if needed
    """
    global PAUSE_STATE_START_TIME
    
    if serverstate.PAUSE_STATE:
        if PAUSE_STATE_START_TIME is None:
            PAUSE_STATE_START_TIME = time.time()
            logging.info("State pause started - timer initiated")
        elif time.time() - PAUSE_STATE_START_TIME > 60:  # 60 seconds timeout
            logging.info("State has been paused for over 60 seconds - forcing reconnect")
            PAUSE_STATE_START_TIME = None
            
            # Force reconnect in a separate thread to avoid blocking
            def force_reconnect():
                try:
                    if hasattr(serverstate, 'STATE') and serverstate.STATE and hasattr(serverstate.STATE, 'ip'):
                        current_ip = serverstate.STATE.ip
                        if current_ip:
                            logging.info(f"Force reconnecting to current server: {current_ip}")
                            serverstate.connect(current_ip)
                        else:
                            logging.info("No current IP found, trying to get new server")
                            new_ip = servers.get_most_popular_server()
                            if new_ip:
                                serverstate.connect(new_ip)
                            else:
                                api.exec_command("reconnect")
                    else:
                        logging.info("No state available, using basic reconnect command")
                        api.exec_command("reconnect")
                except Exception as e:
                    logging.error(f"Force reconnect failed: {e}")
                    api.exec_command("reconnect")
            
            reconnect_thread = threading.Thread(target=force_reconnect)
            reconnect_thread.daemon = True
            reconnect_thread.start()
    else:
        # Reset timer when state is no longer paused
        if PAUSE_STATE_START_TIME is not None:
            PAUSE_STATE_START_TIME = None
            logging.info("State unpaused - timer reset")


def handle_error_with_delay(error_line, error_action):
    """
    Handle error detection with a 5-second delay before executing the action
    """
    global LAST_ERROR_TIME
    
    if error_action == "RECONNECT":
        logging.info(f"Error detected: {error_line}")
        logging.info("Scheduling reconnect in 5 seconds...")
        
        # Use threading to avoid blocking the main console reading loop
        def delayed_reconnect():
            time.sleep(5)
            logging.info("Executing delayed reconnect...")
            
            # Use the proper serverstate reconnect function instead of just the command
            # This ensures proper state management and connection flow
            if hasattr(serverstate, 'STATE') and serverstate.STATE and hasattr(serverstate.STATE, 'ip'):
                current_ip = serverstate.STATE.ip
                if current_ip:
                    logging.info(f"Reconnecting to current server: {current_ip}")
                    serverstate.connect(current_ip)
                else:
                    logging.info("No current IP found, using basic reconnect command")
                    api.exec_command("reconnect")
            else:
                logging.info("No state available, using basic reconnect command")
                api.exec_command("reconnect")
        
        reconnect_thread = threading.Thread(target=delayed_reconnect)
        reconnect_thread.daemon = True
        reconnect_thread.start()
        
    elif error_action == "DIFFERENT_IP":
        logging.info(f"Error detected: {error_line}")
        logging.info("Scheduling IP change reconnect in 5 seconds...")
        
        def delayed_ip_reconnect():
            time.sleep(5)
            logging.info("Executing delayed IP reconnect...")
            try:
                new_ip = servers.get_next_active_server([serverstate.CURRENT_IP] if serverstate.CURRENT_IP else [])
                if new_ip:
                    logging.info(f"Connecting to different server: {new_ip}")
                    serverstate.connect(new_ip)
                else:
                    logging.error("Could not get a different server IP, trying basic reconnect")
                    api.exec_command("reconnect")
            except Exception as e:
                logging.error(f"Failed to get different server: {e}, trying basic reconnect")
                api.exec_command("reconnect")
        
        reconnect_thread = threading.Thread(target=delayed_ip_reconnect)
        reconnect_thread.daemon = True
        reconnect_thread.start()


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
            # Check pause timeout during idle periods
            check_pause_timeout()
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
            if (len(LOG) > 5000):
                LOG = LOG[1000:]

            # if line_data.pop("command") is not None:
            if 'command' in line_data and line_data['command'] is not None:
                command = line_data['command']
                handle_command = getattr(cmd, f"handle_{command}")
                try:
                    handle_command(line_data)
                except Exception as e:
                    logging.info(f"Error occurred for in-game command {command}: {e}")
            if ("report written to system/reports/" in line_data["content"]):
                # Skip system messages entirely
                pass
            elif line_data["type"] in ["PRINT", "SAY", "ANNOUNCE", "RENAME", "CONNECTED", 
                                       "DISCONNECTED", "ENTEREDGAME", "JOINEDSPEC", 
                                       "REACHEDFINISH", "YOURRANK"]:
                
                # Only delay player messages (SAY, REACHEDFINISH), send others immediately
                if line_data["type"] in ["SAY", "REACHEDFINISH"]:
                    # Add to delay queue
                    DELAYED_MESSAGE_QUEUE.append({
                        'message': line_data,
                        'send_time': time.time() + 2  # 2 second delay
                    })
                else:
                    # Send system messages immediately
                    CONSOLE_DISPLAY.append(line_data)
                    WS_Q.put(json.dumps({'action': 'message', 'message': line_data}))

            # Check pause timeout after processing each line
            check_pause_timeout()


def message_to_id(msg):
    return blake2b(bytes(msg, "utf-8"), digest_size=8, salt=os.urandom(blake2b.SALT_SIZE)).hexdigest()


# Not the most accurate way, but it works for most players
# The only exception is when a player has (:) in their name
def is_server_msg(line, msg):
    data = line[:line.index(msg)]

    return ':' not in data


def process_line(line):
    """
    Processes a console line into a more useful format. Extracts type (say, announcement, print) as well as author
    and content if applicable.
    :param line: Console line to be processed
    :return: Data dictionary containing useful data about the line
    """

    global ERROR_FILTERS
    global LAST_ERROR_TIME
    global PREVIOUS_LINE
    global PAUSE_STATE_START_TIME  # Add this to global access

    line = line.strip()

    line_data = {
        "id": message_to_id(f"{time.time()}_MISC"),
        "type": "MISC",
        "command": None,
        "author": None,
        "content": line,
        "timestamp": time.time()
    }

    # you can add more errors like this: ['error1', 'error2', 'error3']
    errors = ['ERROR: Unhandled exception cought']

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
                # Reset the timer when pause state is set
                PAUSE_STATE_START_TIME = None

        if line in ERROR_FILTERS:
            if LAST_ERROR_TIME is None or time.time() - LAST_ERROR_TIME >= 10:
                LAST_ERROR_TIME = time.time()
                logging.info(f"Previous line: {PREVIOUS_LINE}")
                handle_error_with_delay(line, ERROR_FILTERS[line])

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
            
            # Extract the vote content to check if it's a kick vote against the bot
            vote_content = line[line.index('called a vote:') + len('called a vote:'):].strip()
            bot_name = None
            
            # Get bot's name from state
            if hasattr(serverstate, 'STATE') and serverstate.STATE:
                bot_player = serverstate.STATE.get_player_by_id(serverstate.STATE.bot_id)
                if bot_player:
                    bot_name = bot_player.n
            
            # Check if this is a kick vote targeting the bot
            is_bot_kick = False
            if 'kick' in vote_content.lower() or 'clientkick' in vote_content.lower():
                # Remove color codes for better matching
                clean_vote_content = re.sub(r'\^.', '', vote_content.lower())
                clean_bot_name = re.sub(r'\^.', '', bot_name.lower()) if bot_name else ''
                
                # Common variations of the bot name to check for
                bot_name_patterns = ['defrag.live', 'defraglive', 'defrag live']
                
                # Check if bot's name appears in the vote content
                if clean_bot_name and clean_bot_name in clean_vote_content:
                    is_bot_kick = True
                    logging.info(f"Detected kick vote against bot by name: {vote_content}")
                else:
                    # Check common bot name patterns
                    for pattern in bot_name_patterns:
                        if pattern in clean_vote_content:
                            is_bot_kick = True
                            logging.info(f"Detected kick vote against bot by pattern '{pattern}': {vote_content}")
                            break
            
            if is_bot_kick:
                # Always vote F2 (no) when someone tries to kick the bot
                logging.info("Voting F2 to reject kick vote against bot.")
                api.exec_command("vote no")
                api.exec_command("say ^7Vote to kick me detected. Voted ^1f2^7.")
            elif serverstate.STATE.num_players == 2:  # only bot and 1 other player in game, always f1
                logging.info("1 other player in server, voting yes.")
                api.exec_command("vote yes")
                api.exec_command("say ^7Vote detected. Voted ^3f1^7.")
            else:
                logging.info("Multiple people in server, initiating vote tally.")
                serverstate.STATE.init_vote()
                api.exec_command("say ^7Vote detected. Should I vote yes or no? Send ^3?^7f1 for yes and ^3?^7f2 for no.")

        if line.startswith('Com_TouchMemory:'):
            time.sleep(3)
            api.exec_command("team s;svinfo_report serverstate.txt;svinfo_report initialstate.txt")
            serverstate.initialize_state(True)
            serverstate.PAUSE_STATE = False
            # Reset timer when pause state is cleared
            PAUSE_STATE_START_TIME = None

        if line.startswith('Not recording a demo.') or line.startswith("report written to system/reports/initialstate.txt"):
            if serverstate.CONNECTING:
                time.sleep(1)
                serverstate.CONNECTING = False
            elif serverstate.VID_RESTARTING:
                time.sleep(1)
                logging.info("vid_restart done.")
                serverstate.PAUSE_STATE = False
                serverstate.VID_RESTARTING = False
                # Reset timer when pause state is cleared
                PAUSE_STATE_START_TIME = None
            elif serverstate.PAUSE_STATE:
                time.sleep(1)
                serverstate.PAUSE_STATE = False
                logging.info("Game loaded. Continuing state.")
                serverstate.STATE.say_connect_msg()
                # Reset timer when pause state is cleared
                PAUSE_STATE_START_TIME = None

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
            # Prints have their ending quotation mark on the next line, very strange
            print_r = r"^print\s*\"(.*?)$"
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
    PREVIOUS_LINE = line_data
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

        slice = LOG[length:length_new]

        logging.info("MORE", slice)

        for line in slice:
            if check_line(line, end_type, end_author, end_content, end_content_fuzzy):
                logging.info("FOUND", line)
                return line

        time.sleep(delay)

def process_delayed_messages():
    """Background thread to process delayed messages"""
    global DELAYED_MESSAGE_QUEUE
    while True:
        current_time = time.time()
        # Check for messages ready to be sent
        messages_to_send = []
        remaining_messages = []
        
        for delayed_msg in DELAYED_MESSAGE_QUEUE:
            if current_time >= delayed_msg['send_time']:
                messages_to_send.append(delayed_msg['message'])
            else:
                remaining_messages.append(delayed_msg)
        
        # Send ready messages
        for msg in messages_to_send:
            logging.info(f"Sending delayed message: {msg['type']} - {msg['content'][:50]}...")
            CONSOLE_DISPLAY.append(msg)
            WS_Q.put(json.dumps({'action': 'message', 'message': msg}))
        
        # Update queue
        DELAYED_MESSAGE_QUEUE = remaining_messages
        
        time.sleep(0.1)  # Check every 100ms

# Start the delay processor thread (add this in the read() function after STOP_CONSOLE = False)
delay_processor = threading.Thread(target=process_delayed_messages)
delay_processor.daemon = True
delay_processor.start()