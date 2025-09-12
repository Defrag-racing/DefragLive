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
import websocket_console

LOG = []
CONSOLE_DISPLAY = []
FILTERS = ["R_AddMD3Surfaces"]
WS_Q = queue.Queue()
STOP_CONSOLE = False
PREVIOUS_LINE = ''
LAST_ERROR_TIME = None
PAUSE_STATE_START_TIME = None  # Add this global variable
DELAYED_MESSAGE_QUEUE = []
MAP_ERROR_COUNTDOWN_ACTIVE = False
SENT_MESSAGE_IDS = set()
WEBSOCKET_LAST_HEALTHY = time.time()  # Track websocket health

ERROR_FILTERS = {
    "ERROR: CL_ParseServerMessage:": "RECONNECT",
    "Exception Code: ACCESS_VIOLATION": "RECONNECT",
    "Signal caught (11)": "RECONNECT",
    "Incorrect challenge, please reconnect": "RECONNECT",
    "ERROR: CL_ParseServerMessage: read past end of server message": "RECONNECT",
    "^0^7D^6e^7Frag^6.^7LIVE^0/^7 was kicked": "RECONNECT",
    "ERROR: CM_LoadMap: couldn't load maps/": "MAP_ERROR",
    "Server connection timed out": "RECONNECT"
}

# System message patterns that should be filtered out completely
SYSTEM_MESSAGE_PATTERNS = [
    "------ Server Initialization ------",
    "------- Game Initialization -------",
    "-----------------------------------",
    "---------------------------",  # Added this missing pattern
    "----- Server Shutdown",
    "==== ShutdownGame ====",  # Added shutdown message
    "Server:",
    "gamename:",
    "gamedate:",
    "teams with",
    "items registered",
    "Loading vm file",
    "VM file",
    "loaded in",
    "bytes on the hunk",
    "arenas parsed",
    "arenas ignored",
    "bots parsed",
    "VM_LoadDll",
    "leaked filehandle",
    "succeeded!",
    "Loading dll file",
    "^7[^1m^3D^1d^7] cgame-proxy",  # cgame proxy messages
    "Missing { in info file",
    "files in",
    "pk3 files",
    "Hunk_Clear: reset the hunk ok",
    "GAMMA: hardware",
    "texturemode:",
    "texture bits:",
    "picmip:",
    "Initializing Shaders",
    "WARNING: Ignoring shader file",
    "WARNING: server is not allowed to set",
    "Ignoring entire file",
    "stitched",
    "LoD cracks",
    "loaded",
    "faces,",
    "meshes,",
    "trisurfs,",
    "flares",
    "WARNING: light grid mismatch",
    "found",
    "VBO surfaces",
    "vertexes,",
    "indexes",
    "recording to demos/",  
    "VM_LoadDLL",
    "msec",
    "^2Cvar:",
    "test: okay"
]

def handle_map_error_with_countdown():
    """
    Handle map loading error with 60-second countdown and auto-reconnect
    """
    global MAP_ERROR_COUNTDOWN_ACTIVE, DELAYED_MESSAGE_QUEUE
    
    if MAP_ERROR_COUNTDOWN_ACTIVE:
        return  # Already running countdown
    
    MAP_ERROR_COUNTDOWN_ACTIVE = True
    logging.info("Map loading error detected. Starting 60-second countdown...")
    
    def countdown_and_reconnect():
        global MAP_ERROR_COUNTDOWN_ACTIVE, DELAYED_MESSAGE_QUEUE
        
        try:
            for seconds_left in range(60, 0, -5):  # Count down from 60 in 5-second intervals
                # Create countdown message and add to delayed queue
                countdown_msg = {
                    'id': message_to_id(f"MAP_COUNTDOWN_{seconds_left}_{time.time()}"),
                    'type': 'MAP_COUNTDOWN',
                    'author': None,
                    'content': f"^1Map update required. ^7Reconnecting in ^3{seconds_left} ^7seconds...",
                    'timestamp': time.time(),
                    'command': None
                }
                
                # Add to delayed queue for immediate processing
                DELAYED_MESSAGE_QUEUE.append({
                    'message': countdown_msg,
                    'send_time': time.time()  # Send immediately
                })
                
                logging.info(f"Map error countdown: {seconds_left} seconds remaining")
                time.sleep(5)
            
            # Final reconnect message
            final_msg = {
                'id': message_to_id(f"MAP_COUNTDOWN_FINAL_{time.time()}"),
                'type': 'MAP_COUNTDOWN', 
                'author': None,
                'content': f"^3Reconnecting now...",
                'timestamp': time.time(),
                'command': None
            }
            
            DELAYED_MESSAGE_QUEUE.append({
                'message': final_msg,
                'send_time': time.time()
            })
            
            logging.info("Map error countdown complete. Using smart recovery...")
            
            # Wait a moment then use smart recovery
            time.sleep(2)
            
            # Use smart recovery instead of direct reconnect
            serverstate.smart_connection_recovery("Map loading error countdown completed")
                
        except Exception as e:
            logging.error(f"Error during map error countdown: {e}")
            serverstate.smart_connection_recovery("Map error countdown failed")
        finally:
            MAP_ERROR_COUNTDOWN_ACTIVE = False
    
    # Start countdown in separate thread
    countdown_thread = threading.Thread(target=countdown_and_reconnect)
    countdown_thread.daemon = True
    countdown_thread.start()

#def check_pause_timeout():
#    """
#    Check if state has been paused for too long and trigger reconnect if needed
#    """
#    global PAUSE_STATE_START_TIME
#    
#    if serverstate.PAUSE_STATE:
#        if PAUSE_STATE_START_TIME is None:
#            PAUSE_STATE_START_TIME = time.time()
#            logging.info("State pause started - timer initiated")
#        elif time.time() - PAUSE_STATE_START_TIME > 60:  # 60 seconds timeout
#            logging.info("State has been paused for over 60 seconds - forcing reconnect")
#            PAUSE_STATE_START_TIME = None
#            
#            # Force reconnect in a separate thread to avoid blocking
#            def force_reconnect():
#                try:
#                    if hasattr(serverstate, 'STATE') and serverstate.STATE and hasattr(serverstate.STATE, 'ip'):
#                        current_ip = serverstate.STATE.ip
#                        if current_ip:
#                            logging.info(f"Force reconnecting to current server: {current_ip}")
#                            serverstate.connect(current_ip)
#                        else:
#                            logging.info("No current IP found, trying to get new server")
#                            new_ip = servers.get_most_popular_server()
#                            if new_ip:
#                                serverstate.connect(new_ip)
#                            else:
#                                api.exec_command("reconnect")
#                    else:
#                        logging.info("No state available, using basic reconnect command")
#                        api.exec_command("reconnect")
#                except Exception as e:
#                    logging.error(f"Force reconnect failed: {e}")
#                    api.exec_command("reconnect")
#            
#            reconnect_thread = threading.Thread(target=force_reconnect)
#            reconnect_thread.daemon = True
#            reconnect_thread.start()
#    else:
#        # Reset timer when state is no longer paused
#        if PAUSE_STATE_START_TIME is not None:
#            PAUSE_STATE_START_TIME = None
#            logging.info("State unpaused - timer reset")


def handle_error_with_delay(error_line, error_action):
    """
    Handle error detection with appropriate delays and actions
    """
    global LAST_ERROR_TIME
    
    if error_action == "MAP_ERROR":
        logging.info(f"Map loading error detected: {error_line}")
        handle_map_error_with_countdown()
        return
        
    if error_action == "RECONNECT":
        logging.info(f"Error detected: {error_line}")
        
        # CHECK FOR CRITICAL CRASHES - skip to attempt 2 (reconnect)
        if any(crash_indicator in error_line for crash_indicator in [
            "ACCESS_VIOLATION", 
            "Exception Code:", 
            "Signal caught",
            "forcefully unloading cgame vm"
        ]):
            logging.info("Critical crash detected - skipping state resume, going to reconnect")
            serverstate.RECOVERY_ATTEMPTS = 1  # Skip attempt 1, go to attempt 2
        
        # Reset greeting state on errors so greeting is sent on successful reconnect
        logging.info("Error detected - resetting greeting state for reconnection")
        serverstate.LAST_GREETING_SERVER = None
        
        logging.info("Starting smart recovery for error...")
        serverstate.smart_connection_recovery(f"Game error: {error_line}")
        
    elif error_action == "DIFFERENT_IP":
        logging.info(f"Error detected: {error_line}")
        logging.info("Starting smart recovery for IP change...")
        
        # Use smart recovery but skip to attempt 3 (different server)
        serverstate.RECOVERY_ATTEMPTS = 2  # Skip to different server attempt
        serverstate.smart_connection_recovery(f"IP change error: {error_line}")


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
            #check_pause_timeout()
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
        time.sleep(2)

    STOP_CONSOLE = False

    # Start the delay processor thread here, after STOP_CONSOLE = False
    delay_processor = threading.Thread(target=process_delayed_messages)
    delay_processor.daemon = True
    delay_processor.start()

    with open(file_path, 'r') as log:
        new_lines = read_tail(log)

        for line in new_lines:
            for filter in FILTERS:
                if filter in line:
                    continue

            line_data = process_line(line)

            # ADD NULL CHECK HERE - CRITICAL FIX
            if line_data is None:
                continue

            # Filter
            line_data = filters.filter_line_data(line_data)

            # ADD ANOTHER NULL CHECK AFTER FILTERING
            if line_data is None:
                continue

            LOG.append(line_data)

            # Cut log to size
            if (len(LOG) > 5000):
                LOG = LOG[1000:]

            # SAFE CHECK FOR COMMAND - FIXED
            if line_data and isinstance(line_data, dict) and 'command' in line_data and line_data['command'] is not None:
               command = line_data['command']
               handle_command = getattr(cmd, f"handle_{command}")
               try:
                   handle_command(line_data)
               except Exception as e:
                   logging.info(f"Error occurred for in-game command {command}: {e}")
            if (("report written to system/reports/" in line_data["content"]) or
                ("Com_TouchMemory:" in line_data["content"]) or
                ("CL_InitCGame:" in line_data["content"])):
               # Skip connection/system messages from extension
               pass
            elif line_data["type"] in ["PRINT", "SAY", "ANNOUNCE", "RENAME", "CONNECTED", 
                                      "DISCONNECTED", "ENTEREDGAME", "JOINEDSPEC", 
                                      "REACHEDFINISH", "YOURRANK", "MAP_ERROR", "MAP_COUNTDOWN",
                                      "SERVERRECORD", "FIRSTTIME", "LOGGEDIN"]:
                
                # Filter out bot tell responses before queueing
                if (line_data["type"] == "SAY" and 
                    line_data.get("author") and "DefragLive" in str(line_data["author"]) and
                    line_data.get("content") and 
                    any(phrase in line_data["content"] for phrase in [
                        "Detected nospec,",
                        "To disable private notifications",
                        "nospec active,",
                        "cant spectate"
                    ])):
                    # Skip queueing tell responses
                    pass
                else:
                    # Delay ALL other messages by 2 seconds
                    DELAYED_MESSAGE_QUEUE.append({
                        'message': line_data,
                        'send_time': time.time() + 2  # 2 second delay for everything
                    })

def message_to_id(msg):
    return blake2b(bytes(msg, "utf-8"), digest_size=8, salt=os.urandom(blake2b.SALT_SIZE)).hexdigest()


# Not the most accurate way, but it works for most players
# The only exception is when a player has (:) in their name
def is_server_msg(line, msg):
    data = line[:line.index(msg)]

    return ':' not in data


def is_system_message(line):
    """Check if a line contains system initialization or shutdown messages"""
    global SYSTEM_MESSAGE_PATTERNS
    
    # Don't filter proxy command separator lines (they start with color codes)
    if line.startswith("^") and "-----" in line:
        return False  # This is a proxy separator, not a system message
    
    for pattern in SYSTEM_MESSAGE_PATTERNS:
        if pattern in line:
            return True
    return False


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
    global PAUSE_STATE_START_TIME
    
    line = line.strip()

    # ADD DEADLOCK CHECK EARLY
    if hasattr(serverstate, 'check_recovery_deadlock'):
        try:
            if serverstate.check_recovery_deadlock():
                logging.critical("Emergency recovery deadlock reset triggered from console")
        except Exception as e:
            logging.error(f"Error in deadlock check: {e}")

    # SET PAUSE TIMER AND ENHANCED TIMEOUT LOGIC
    # Set pause timer if not set
    if serverstate.PAUSE_STATE and PAUSE_STATE_START_TIME is None:
        PAUSE_STATE_START_TIME = time.time()
        logging.info("Pause timer started")
    
    # Check for absolute timeout if connection tracking exists
    if hasattr(serverstate, 'CONNECTION_START_TIME') and serverstate.CONNECTION_START_TIME:
        total_stuck_time = time.time() - serverstate.CONNECTION_START_TIME
        if total_stuck_time > 120:  # 2 minutes absolute timeout
            logging.error(f"ABSOLUTE TIMEOUT: Bot stuck for {total_stuck_time}s")
            try:
                serverstate.force_connection_recovery("Absolute timeout exceeded")
            except Exception as e:
                logging.error(f"Force recovery failed: {e}")
            return
    
    # Progressive timeout checks - more lenient and uses smart recovery
    if serverstate.PAUSE_STATE and PAUSE_STATE_START_TIME is not None:
        pause_duration = time.time() - PAUSE_STATE_START_TIME
        
        # More aggressive timeout for recovery situations
        if hasattr(serverstate, 'RECOVERY_IN_PROGRESS') and serverstate.RECOVERY_IN_PROGRESS:
            timeout_limit = 90  # 90 seconds during recovery
        elif serverstate.VID_RESTARTING:
            timeout_limit = 60  # Video restart - more time
        elif serverstate.CONNECTING:
            timeout_limit = 120  # Connection + map loading - much more time
        else:
            timeout_limit = 90  # General pause - more time
        
        if pause_duration > timeout_limit:
            logging.error(f"PAUSE TIMEOUT: State paused for {pause_duration:.0f}s - triggering smart recovery")
            try:
                serverstate.smart_connection_recovery(f"Pause timeout ({pause_duration:.0f}s)")
            except Exception as e:
                logging.error(f"Smart recovery failed: {e}")
                # Emergency fallback
                logging.critical("EMERGENCY FALLBACK: Direct standby mode")
                serverstate.PAUSE_STATE = False
                api.exec_command("map st1")

    line_data = {
        "id": message_to_id(f"{time.time()}_MISC"),
        "type": "MISC",
        "command": None,
        "author": None,
        "content": line,
        "timestamp": time.time()
    }

    # EARLY SYSTEM MESSAGE FILTERING - Filter out system messages before any processing
    if is_system_message(line):
        return line_data  # Return as MISC type (won't be queued)

    # Skip renderer initialization messages early - be specific to avoid filtering !top results
    if any(pattern in line for pattern in [
        "R_Init", 
        "finished R_Init"
    ]) or (line.strip() == "----------------------" and "^5" not in line):
        return line_data  # Return as MISC type (won't be queued)

    # you can add more errors like this: ['error1', 'error2', 'error3']
    errors = ['ERROR: Unhandled exception cought']

    # SERVERCOMMAND

    try:
        # Don't log system messages or reports
        if (is_system_message(line) or
            "report written to system/reports/initialstate.txt" in line or 
            "report written to system/reports/serverstate.txt" in line):
            pass
        else:
            logging.info(f"[Q3] {line}")

        # ADD THE MAP LOADING ERROR DETECTION HERE (before the ERROR_FILTERS check):
        if "ERROR: CM_LoadMap: couldn't load maps/" in line:
            # Extract map name from the error
            map_name_match = re.search(r"couldn't load maps/(.+?)\.bsp", line)
            map_name = map_name_match.group(1) if map_name_match else "unknown"
            
            # Create line_data for the map error (this will go through normal processing)
            line_data["id"] = message_to_id(f"MAP_ERROR_{map_name}_{time.time()}")
            line_data["type"] = "MAP_ERROR"
            line_data["author"] = None
            line_data["content"] = f"^1Map loading failed: ^7{map_name}.bsp could not be loaded. ^3Reconnecting in 60 seconds..."
            
            logging.info(f"Map loading error created: {map_name}")

        if line in {"VoteVote passed.", "RE_Shutdown( 0 )"}:
            if not serverstate.PAUSE_STATE:
                serverstate.PAUSE_STATE = True
                logging.info("Game is loading. Pausing state.")
                # Reset the timer when pause state is set
                PAUSE_STATE_START_TIME = None

        # Check for specific error patterns first
        for error_pattern, error_action in ERROR_FILTERS.items():
            if error_pattern in line:
                if LAST_ERROR_TIME is None or time.time() - LAST_ERROR_TIME >= 10:
                    LAST_ERROR_TIME = time.time()
                    logging.info(f"Previous line: {PREVIOUS_LINE}")
                    handle_error_with_delay(line, error_action)
                break

        if line in ERROR_FILTERS:
            if LAST_ERROR_TIME is None or time.time() - LAST_ERROR_TIME >= 10:
                LAST_ERROR_TIME = time.time()
                logging.info(f"Previous line: {PREVIOUS_LINE}")
                handle_error_with_delay(line, ERROR_FILTERS[line])

        if 'broke the server record with' in line and is_server_msg(line, 'broke the server record with'):
            # Extract player name and time from the server record message
            try:
                # Parse the line to extract player name and time
                # Format: "PlayerName broke the server record with 12:496 [other info]"
                player_name = line[:line.index(' broke the server record with')]
                record_part = line[line.index(' broke the server record with') + len(' broke the server record with'):]
                # Extract just the time (before any additional info in brackets or spaces)
                record_time = record_part.split()[0] if record_part else "unknown time"
                
                # Trigger celebration from serverstate.py
                serverstate.handle_world_record_event(player_name, record_time)
                
            except Exception as e:
                logging.error(f"Error parsing server record message: {e}")
                # Fallback - still play sound and trigger celebration without specific details
                api.play_sound("worldrecord.wav")
                serverstate.handle_world_record_event()

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
                api.exec_command("say ^7Vote detected. Voted ^3f1^7.")
                api.exec_command("vote yes")
            else:
                logging.info("Multiple people in server, initiating vote tally.")
                serverstate.STATE.init_vote()
                api.exec_command("say ^7Vote detected. Should I vote yes or no? Send ^3?^7f1 for yes and ^3?^7f2 for no.")

        if serverstate.CONNECTING:
            logging.info(f"[DEBUG] CONNECTING=True, checking line: {line}")

        if (line.startswith('Not recording a demo.') or 
            line.startswith("report written to system/reports/initialstate.txt") or
            line.startswith("Sound memory manager started") or
            line.startswith("CL_InitCGame:") or
            line.startswith("Com_TouchMemory:") or
            "GL_RENDERER:" in line or
            "MODE: -1," in line or
            # ADD THIS NEW CONDITION - detect when bot enters game during connection
            (line.endswith(" entered the game.") and serverstate.CONNECTING and 
             ("DefragLive" in line or "LIVE" in line))):
            
            # Add this debug line as the FIRST line inside the if block
            logging.info(f"[DEBUG] Connection detection triggered by: {line}")
            
            # PRIORITY ORDER: Check most specific conditions first
            if serverstate.VID_RESTARTING:
                # VID_RESTART completion - HIGHEST PRIORITY
                time.sleep(2)
                logging.info("vid_restart done.")
                serverstate.PAUSE_STATE = False
                serverstate.VID_RESTARTING = False
                PAUSE_STATE_START_TIME = None
                
                if hasattr(serverstate, 'RECOVERY_IN_PROGRESS') and serverstate.RECOVERY_IN_PROGRESS:
                    serverstate.reset_recovery_state()
                    logging.info("Connection successful - recovery state cleared")
                
                # Process queued settings first, then sync
                logging.info(f"[SETTINGS DEBUG] Queue size before processing: {len(websocket_console.SETTINGS_QUEUE)}")
                websocket_console.process_queued_settings()
                logging.info(f"[SETTINGS DEBUG] Queue size after processing: {len(websocket_console.SETTINGS_QUEUE)}")
                
                def delayed_vid_restart_sync():
                    import time
                    import websocket_console
                    time.sleep(2)
                    try:
                        websocket_console.sync_current_settings_to_vps()
                        logging.info("Synced settings to VPS after vid_restart")
                    except Exception as e:
                        logging.error(f"Failed to sync settings after vid_restart: {e}")
                
                import threading
                vid_restart_thread = threading.Thread(target=delayed_vid_restart_sync)
                vid_restart_thread.daemon = True
                vid_restart_thread.start()
                
            elif serverstate.CONNECTING:
                # Connection completion - SECOND PRIORITY
                time.sleep(2)
                serverstate.CONNECTING = False
                serverstate.PAUSE_STATE = False
                serverstate.CONNECTION_START_TIME = None  # ADD THIS LINE
                logging.info("Connection complete. Continuing state.")
                
                logging.info(f"DEBUG: About to process queued settings. Queue size: {len(websocket_console.SETTINGS_QUEUE)}")
                
                if hasattr(serverstate, 'RECOVERY_IN_PROGRESS') and serverstate.RECOVERY_IN_PROGRESS:
                    serverstate.reset_recovery_state()
                    logging.info("Connection successful - recovery state cleared")
                
                # GREETING LOGIC - triggered when connection actually completes
                logging.info(f"[GREETING DEBUG] Connection complete - LAST_GREETING_SERVER: {serverstate.LAST_GREETING_SERVER}")
                logging.info(f"[GREETING DEBUG] Connection complete - CURRENT_IP: {serverstate.CURRENT_IP}")
                
                if serverstate.CURRENT_IP and serverstate.CURRENT_IP != serverstate.LAST_GREETING_SERVER:
                    serverstate.LAST_GREETING_SERVER = serverstate.CURRENT_IP
                    logging.info(f"[GREETING DEBUG] Scheduling greeting for {serverstate.CURRENT_IP}")
                    
                    def delayed_nationality_greeting():
                        import time
                        time.sleep(5)
                        logging.info(f"[GREETING DEBUG] Executing greeting for {serverstate.CURRENT_IP}")
                        serverstate.send_nationality_greeting(serverstate.CURRENT_IP)
                    
                    import threading
                    greeting_thread = threading.Thread(target=delayed_nationality_greeting, daemon=True)
                    greeting_thread.start()
                
                PAUSE_STATE_START_TIME = None
                
                # FORCE STATE INITIALIZATION after connection
                def delayed_state_init():
                    import time
                    time.sleep(3)  # Wait for connection to fully establish
                    logging.info("Forcing state initialization after connection")
                    api.exec_command("team s;svinfo_report serverstate.txt;svinfo_report initialstate.txt")
                    serverstate.initialize_state(True)
                
                import threading
                init_thread = threading.Thread(target=delayed_state_init, daemon=True)
                init_thread.start()
                
            elif serverstate.PAUSE_STATE:
                # Game restart completion - THIRD PRIORITY
                # Wait a bit longer to catch immediate crashes after CL_InitCGame
                time.sleep(2)
                
                # Double-check for immediate crashes after CL_InitCGame
                if any(crash_indicator in line for crash_indicator in [
                    "ACCESS_VIOLATION", 
                    "Exception Code:", 
                    "Signal caught",
                    "forcefully unloading cgame vm",
                    "ERROR: Unhandled exception caught"
                ]):
                    logging.info("Immediate crash detected after CL_InitCGame - keeping pause state and triggering recovery")
                    # Don't unpause, let the crash handler deal with it
                    return
                
                serverstate.PAUSE_STATE = False
                logging.info("Game loaded. Continuing state.")
                serverstate.STATE.say_connect_msg()
                PAUSE_STATE_START_TIME = None
                
                if hasattr(serverstate, 'RECOVERY_IN_PROGRESS') and serverstate.RECOVERY_IN_PROGRESS:
                    serverstate.reset_recovery_state()
                    logging.info("Connection successful - recovery state cleared")
                
                # SYNC SETTINGS AFTER GAME RESTART
                def delayed_game_restart_sync():
                    import time
                    import websocket_console
                    time.sleep(2)
                    try:
                        websocket_console.sync_current_settings_to_vps()
                        logging.info("Synced settings to VPS after game restart")
                    except Exception as e:
                        logging.error(f"Failed to sync settings after restart: {e}")
                
                websocket_console.process_queued_settings()
                
                import threading
                game_restart_thread = threading.Thread(target=delayed_game_restart_sync)
                game_restart_thread.daemon = True
                game_restart_thread.start()
            
            # NO else: block - manual restart detection removed
 
        if (line.startswith('Com_TouchMemory:') or 
            ('entered the game.' in line and serverstate.PAUSE_STATE and 
             not serverstate.CONNECTING and not serverstate.VID_RESTARTING)):
            
            # If we're paused but not connecting/restarting, and players are entering
            # This likely means a map change completed but we missed the normal unpause trigger
            if serverstate.PAUSE_STATE:
                logging.info("Map change detected via player entry - unpausing state")
                time.sleep(2)  # Brief delay to let map fully load
                api.exec_command("team s;svinfo_report serverstate.txt;svinfo_report initialstate.txt")
                serverstate.initialize_state(True)
                serverstate.PAUSE_STATE = False
                # Reset timer when pause state is cleared
                PAUSE_STATE_START_TIME = None

        # TIMEOUT FALLBACK - unpause after extended pause (emergency recovery)
        if serverstate.PAUSE_STATE and PAUSE_STATE_START_TIME is not None:
            pause_duration = time.time() - PAUSE_STATE_START_TIME
            # Shorter timeout for vid_restart, longer for other pauses
            timeout_limit = 30 if serverstate.VID_RESTARTING else 50
            
            if pause_duration > timeout_limit:
                logging.warning(f"State paused for {pause_duration:.0f}s - forcing unpause (emergency recovery)")
                try:
                    if serverstate.VID_RESTARTING:
                        logging.info("Force clearing vid_restart state due to timeout")
                        serverstate.VID_RESTARTING = False
                    api.exec_command("team s;svinfo_report serverstate.txt;svinfo_report initialstate.txt")
                    serverstate.initialize_state(True)
                    serverstate.PAUSE_STATE = False
                    PAUSE_STATE_START_TIME = None
                except Exception as e:
                    logging.error(f"Emergency unpause failed: {e}")

        def parse_chat_message(command):
            # CHAT MESSAGE (BY PLAYER) - Improved pattern to handle color codes in names
            chat_message_r = r"^(.*?):\s*\^(\d)(.*)$"
            match = re.match(chat_message_r, command)
            
            if not match:
                raise Exception()
            
            chat_name = match.group(1).strip()  # Remove any trailing spaces
            chat_message = match.group(3)       # The actual message content
            
            # Remove trailing color codes from the name (like ^7 at the end)
            # This handles cases where names have color codes attached: "^3Player^7"
            chat_name = re.sub(r'\^[0-9a-zA-Z]+$', '', chat_name)
            
            # FILTER OUT BOT'S OWN TELL RESPONSES
            if "DefragLive" in chat_name or "LIVE" in chat_name:
                if any(phrase in chat_message for phrase in [
                    "Detected nospec,",
                    "To disable private notifications",
                    "nospec active,",
                    "cant spectate"
                ]):
                    # Don't process as a regular chat message
                    raise Exception()  # This will skip this parsing function
            
            line_data["id"] = message_to_id(f"SAY_{chat_name}_{chat_message}")
            line_data["type"] = "SAY"
            line_data["author"] = chat_name
            line_data["content"] = chat_message
            line_data["command"] = cmd.scan_for_command(chat_message)

        def parse_print(command):
            # PRINT
            # Prints have their ending quotation mark on the next line, very strange
            print_r = r"^print\s*\"(.*?)$"
            match = re.match(print_r, command)

            print_message = match.group(1)

            # FILTER OUT TELL RESPONSES - they shouldn't appear in extension
            if any(phrase in print_message for phrase in [
                "Detected nospec,",
                "To disable private notifications", 
                "nospec active,",
                "cant spectate"
            ]):
                line_data["type"] = "MISC"  # Change to MISC so it won't be queued for extension
                return

            # ENHANCED FILTERING: Filter out empty PRINT messages AND system messages
            if (not print_message or print_message.strip() == ""):
                line_data["type"] = "MISC"  # Change to MISC so it won't be queued
                return

            line_data["id"] = message_to_id(f"PRINT_{print_message}")
            line_data["type"] = "PRINT"
            line_data["author"] = None
            line_data["content"] = print_message

        def parse_proxy_results(command):
            # Handle all proxy command responses
            if (command.startswith("^3  Rankings on") or           
                "'s Time History on" in command or                 
                (command.startswith("^3  ") and "cet" in command) or  # Timehistory data
                (command.startswith("^3   ") and ". ^7" in command and "reached the finish line" not in command) or  # !top entries
                "'s Personal Best:" in command or                  
                (command.startswith("^5") and "-----" in command) or # Separators
                "Players Identified Online" in command or           # !who header
                (command.startswith("^5") and "<-" in command) or   # !who entries
                (command.startswith("^1-> ^2")) or                  # !version responses
                ("is rank" in command and "of" in command and "with" in command) or   # !time responses
                "Recent Maps" in command or                         # !recent header
                (command.startswith("^3") and len(command.split()) >= 3 and not "cet" in command and ":" not in command) or  # !recent entries
                "Map Information for" in command or                 # !mapinfo header
                (command.startswith("^3 ") and ("Weapons:" in command or "Items:" in command or "Functions:" in command or "Created:" in command)) or  # !mapinfo entries
                # IMPROVED GENERIC FALLBACK: More specific to avoid catching chat messages
                (command.startswith("^3") and ("/" in command or ":" in command) and 
                 not re.match(r"^.*?\^?[0-9a-zA-Z]*:\s*\^[0-9]", command)) or  # Exclude chat message pattern
                command.strip() == ""):                            # Empty lines
                
                line_data["id"] = message_to_id(f"PRINT_PROXY_{command}")
                line_data["type"] = "PRINT"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

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
                
                # ADD THIS: Trigger automatic +scores refresh
                import threading
                import time
                
                def delayed_scores_refresh():
                    time.sleep(2)  # Wait 2 seconds after player enters
                    try:
                        import config
                        import api
                        #key = config.get_bind("+scores")
                        #logging.info(f"Auto-refreshing scores for new player: {command}")
                        #api.hold_key(key, 0.0001)
                        pass
                    except Exception as e:
                        logging.error(f"Failed to auto-refresh scores: {e}")
                
                # Run in separate thread to avoid blocking
                refresh_thread = threading.Thread(target=delayed_scores_refresh, daemon=True)
                refresh_thread.start()
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

        def parse_server_record(command):
            if ' broke the server record with ' in command:
                line_data["id"] = message_to_id(f"SERVERRECORD_{command}")
                line_data["type"] = "SERVERRECORD"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_first_time(command):
            if ' sets the first time with ' in command:
                line_data["id"] = message_to_id(f"FIRSTTIME_{command}")
                line_data["type"] = "FIRSTTIME"
                line_data["author"] = None
                line_data["content"] = command
            else:
                raise Exception()

        def parse_logged_in(command):
            if ', you are now logged in as ' in command:
                line_data["id"] = message_to_id(f"LOGGEDIN_{command}")
                line_data["type"] = "LOGGEDIN"
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

        for fun in [parse_proxy_results,
                    parse_chat_message,
                    parse_print,
                    parse_scores,
                    parse_rename,
                    parse_connected,
                    parse_disconnected,
                    parse_entered_game,
                    parse_joined_spec,
                    parse_reached_finish,
                    parse_server_record,
                    parse_first_time,
                    parse_logged_in,
                    parse_your_rank]:
            try:
                fun(line)
                break
            except Exception:
                continue
    except Exception as e:
        logging.error(f"Error processing line: {e}")
        return line_data

    # ENSURE we always return a valid dict (add at the very end)
    if line_data is None:
        line_data = {
            "id": message_to_id(f"{time.time()}_FALLBACK"),
            "type": "MISC",
            "command": None,
            "author": None,
            "content": line.strip() if line else "",
            "timestamp": time.time()
        }

    PREVIOUS_LINE = line_data
    return line_data

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
        except Exception:
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

SENT_MESSAGE_IDS = set()  # Add this at the top of console.py

def check_websocket_health():
    """Check if websocket connection is healthy - log status only, don't clear messages"""
    global DELAYED_MESSAGE_QUEUE, WEBSOCKET_LAST_HEALTHY
    
    current_time = time.time()
    websocket_unhealthy_duration = current_time - WEBSOCKET_LAST_HEALTHY
    
    # Log websocket health status but don't clear messages - let extension handle delivery
    if websocket_unhealthy_duration > 60:
        if DELAYED_MESSAGE_QUEUE:
            queue_size = len(DELAYED_MESSAGE_QUEUE)
            # Only log every 30 seconds to avoid spam
            if int(websocket_unhealthy_duration) % 30 == 0:
                logging.info(f"Websocket unhealthy for {int(websocket_unhealthy_duration)}s - {queue_size} messages queued for delivery")

def update_websocket_health():
    """Update websocket health timestamp - called when websocket successfully sends"""
    global WEBSOCKET_LAST_HEALTHY
    WEBSOCKET_LAST_HEALTHY = time.time()

def process_delayed_messages():
    """Background thread to process delayed messages"""
    global DELAYED_MESSAGE_QUEUE, SENT_MESSAGE_IDS
    
    while True:
        # Check websocket health and clear stale messages
        check_websocket_health()
        
        current_time = time.time()
        messages_to_send = []
        remaining_messages = []
        
        for delayed_msg in DELAYED_MESSAGE_QUEUE:
            if current_time >= delayed_msg['send_time']:
                msg = delayed_msg['message']
                msg_id = msg.get('id')
                
                # Skip if already sent - THIS IS THE KEY FIX
                if msg_id not in SENT_MESSAGE_IDS:
                    messages_to_send.append(msg)
                    SENT_MESSAGE_IDS.add(msg_id)
            else:
                remaining_messages.append(delayed_msg)
        
        # Clean up old message IDs periodically
        if len(SENT_MESSAGE_IDS) > 500:
            SENT_MESSAGE_IDS = set(list(SENT_MESSAGE_IDS)[-250:])
        
        # Send ready messages and update health on successful sends
        for msg in messages_to_send:
            logging.info(f"Sending delayed message: {msg['type']} - {msg['content'][:50]}...")
            CONSOLE_DISPLAY.append(msg)
            WS_Q.put(json.dumps({'action': 'message', 'message': msg}))
            # Update health timestamp when we successfully queue a message
            update_websocket_health()
        
        DELAYED_MESSAGE_QUEUE = remaining_messages
        time.sleep(0.1)