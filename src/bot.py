# bot.py
import os  # for importing env vars for the bot to use
from twitchio.ext import commands
import config
import api
import subprocess
import servers
import time
import console
import serverstate
import websocket_console
from env import environ
import threading
import asyncio
from multiprocessing import Process
import logging
from datetime import datetime
import sys
import twitch_commands
import filters
import psutil

# Write PID to file at startup
with open("bot_pid.txt", "w") as f:
    f.write(str(os.getpid()))

df_channel = environ['CHANNEL'] if 'CHANNEL' in environ and environ['CHANNEL'] != "" else input("Your twitch channel name: ")

# To add any sound command, add the command name to the list of commands
# then add the sound file to the music/common/ directory in the /defrag/ folder
# Note: sound file name music be the same as command name (without $)
SOUND_CMDS = [
    '$4ity',
    '$holy'
]

# Twitch commands that start with (?), to add a command
# add it as an array inside this array, where multiple entries
# are aliases, and the first entry is the actual command
# also add the function of the command inside twitch_commands.py
# (command function must be named as the first entry of your command)
TWITCH_CMDS = [
    ["restart"],
    ["triggers"],
    ["clips"],
    ["clear"],
    ["lagometer"],
    ["snaps"],
    ["cgaz"],
    ["nodraw"],
    ["angles"],
    ["obs"],
    ["drawgun"],
##    ["clean"],
    ["sky"],
    ["speedinfo"],
    ["speedorig"],
    ["gibs"],
    ["blood"],
    ["thirdperson"],
    ["miniview"],
    ["inputs"],
    ["slick"],
    ["n1"],
    ["map"],
    ["check"],
##    ["speclist"],
    ["spec"],
    ["brightness"],
    ["picmip"],
    ["fullbright"],
    ["gamma"],
    ["connect", "c"],
    ["reshade"],
    ["reload"],
    ["next", "n"],
    ["prev", "p"],
##    ["scores", "scoreboard","score","scoreboards","scr","sc","scrs","scors","scroes","scar","scora","sorces","scoars","scs","scrose"],
    ["server", "sv"],
    ["ip"],
    ["howmany"],
    ["greeting"],
    ["afk"]
]

# bot setup
bot = commands.Bot(
    token=environ['TMI_TOKEN'],
    irc_token=environ['TMI_TOKEN'],
    client_id=environ['CLIENT_ID'],
    nick=environ['BOT_NICK'],
    prefix=environ['BOT_PREFIX'],
    initial_channels=[df_channel]
)


@bot.event()
async def event_ready():
    """Called once when the bot goes online."""
    logging.info(f"{environ['BOT_NICK']} is online!")
    # Get the channel object using bot.get_channel() and send the message
    channel = bot.get_channel(df_channel)
    await channel.send("/me has landed!")


@bot.event()
async def event_message(ctx):
    """Activates for every message"""
    debounce = 1  # interval between consecutive commands and messages
    author = ctx.author.name if ctx.author else "Unknown"  # Check if author exists
    message = ctx.content

    if ";" in message:  # prevent q3 command injections
        message = message[:message.index(";")]

    # bot.py, at the bottom of event_message
    if message.startswith("?"):  # spectator client customization and controls
        message = message.strip('?').lower()
        split_msg = message.split(' ')
        cmd = split_msg[0]
        args = split_msg[1:] if len(split_msg) > 0 else None
        logging.info(f"TWITCH COMMAND RECEIVED: '{cmd}' from user '{author}'")

        for command in TWITCH_CMDS:
            if cmd in command:
                twitch_function = getattr(twitch_commands, command[0])
                await twitch_function(ctx, author, args)
        time.sleep(debounce)

    elif message.startswith(">") or message.startswith("<"):  # chat bridge
        if serverstate.PAUSE_STATE or serverstate.CONNECTING:
            logging.info(f"Blocked chat bridge message during pause/connecting: {message}")
            return
            
        message = message.lstrip('>').lstrip('<').lstrip(' ')
        blacklisted_words = config.get_list("blacklist_chat")

        for word in blacklisted_words:
            if word in message:
                logging.info(f"Blacklisted word '{word}' detected in message \"{message}\" by \"{author}\". Aborting message.")
                return

        if author.lower() == 'nightbot'.lower():  # ignore twitch Nightbot's name
            author = ''
            author_color_char = 0
        else:
            author += ' ^7> '
            author_color_char = author[0]

        api.exec_command(f"say ^{author_color_char}{author} ^2{message}")
        logging.info("Chat message sent")
        time.sleep(debounce)

    elif message.startswith("**"):  # team chat bridge
        message = message.lstrip('**')
        blacklisted_words = config.get_list("blacklist_chat")

        for word in blacklisted_words:
            if word in message:
                logging.info(f"Blacklisted word '{word}' detected in message \"{message}\" by \"{author}\". Aborting message.")
                return

        if author.lower() == 'nightbot'.lower():  # ignore twitch Nightbot's name
            author = ''
            author_color_char = 0
        else:
            author += ' ^7> '
            author_color_char = author[0]

        api.exec_command(f"say_team ^{author_color_char}{author} ^5{message}")
        logging.info("Chat message sent")
        time.sleep(debounce)

    elif message.startswith("!"):  # proxy mod commands (!top, !rank, etc.)
        logging.info("proxy command received")
        api.exec_command(message)
        time.sleep(debounce)

    elif message.startswith("$"):  # viewer sound commands
        for sound_cmd in SOUND_CMDS:
            if message.startswith(sound_cmd):
                logging.info(f"Sound command received ({sound_cmd})")
                api.play_sound(sound_cmd.replace('$', '') + '.wav') # .wav format only
                time.sleep(debounce)
    return


def launch():
    if environ['DEVELOPMENT']:
        launch_ip = servers.get_least_popular_server()
    else:
        launch_ip = servers.get_most_popular_server()

    if not os.path.isfile(config.DF_EXE_PATH):
        logging.info("Could not find engine or it was not provided. You will have to start the engine and the bot manually. ")
        return None

    # Make sure to set proper CWD when using subprocess.Popen from another directory
    # iDFe will automatically take focus when launching
    subprocess.Popen(args=[config.DF_EXE_PATH, "+cl_title", "TwitchBot Engine", "+con_title", "TwitchBot Console", "+connect", launch_ip], cwd=os.path.dirname(config.DF_EXE_PATH))


if __name__ == "__main__":
    config.read_cfg()
    window_flag = False

    filters.init()

    twitchbot_logfile = f'{datetime.now().strftime("%m-%d-%Y_%H-%M-%S")}_twitchbot.log'
    file_handler = logging.FileHandler(filename=os.path.join(environ['LOG_DIR_PATH'], twitchbot_logfile))
    stdout_handler = logging.StreamHandler(sys.stdout)
    handlers = [file_handler, stdout_handler]
    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S', level=logging.INFO, handlers=handlers)

    try:
        api.api_init()
        window_flag = True
        logging.info("Found defrag window.")
    except Exception as e:
        logging.info(f"Defrag not running, starting... Error: {e}")
        df_process = Process(target=launch)
        df_process.start()
        time.sleep(15)

    from multiprocessing import Process

    logfile_path = config.DF_DIR + '\\qconsole.log'
    con_thread = threading.Thread(target=console.read, args=(logfile_path,), daemon=True)
    con_thread.start()

    serverstate_thread = threading.Thread(target=serverstate.start, daemon=True)
    serverstate_thread.start()

    if config.DEVELOPMENT:
        flask_thread = threading.Thread(target=websocket_console.app.run,
                                        daemon=True,
                                        kwargs={
                                            'host': environ['FLASK_SERVER']['host'],
                                            'port': environ['FLASK_SERVER']['port'],
                                        }
        )
    else:
        flask_thread = threading.Thread(target=websocket_console.run_flask_server,
                                        daemon=True,
                                        kwargs={
                                            'host': environ['FLASK_SERVER']['host'],
                                            'port': environ['FLASK_SERVER']['port']
                                        }
        )

    flask_thread.start()

    ws_loop = asyncio.new_event_loop()
    ws_thread = threading.Thread(target=websocket_console.ws_worker, args=(console.WS_Q, ws_loop,), daemon=True)
    ws_thread.start()

    bot_thread = threading.Thread(target=bot.run, daemon=True)
    bot_thread.start()

    def add_periodic_health_check():
        last_api_success = time.time()

        def health_check_worker():
            nonlocal last_api_success
            while True:
                time.sleep(30)  # Check every 30 seconds

                current_time = time.time()

                # Check if API calls are working (game is responsive)
                try:
                    api.api_init()
                    last_api_success = current_time
                except Exception:
                    # If API fails for more than 2 minutes, kill the game process
                    if current_time - last_api_success > 120:
                        logging.critical("=" * 60)
                        logging.critical("HEALTH CHECK: GAME PROCESS KILL TRIGGERED")
                        logging.critical(f"Game has been unresponsive for {current_time - last_api_success:.0f} seconds")
                        logging.critical(f"Last successful API call: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_api_success))}")
                        logging.critical(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))}")
                        try:
                            killed_processes = []
                            # Find and kill defrag processes
                            for proc in psutil.process_iter(['pid', 'name']):
                                if any(name in proc.info['name'].lower() for name in ['defrag', 'quake', 'iodfe', 'ioq3']):
                                    killed_processes.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                                    logging.critical(f"HEALTH CHECK: Killing unresponsive game process {proc.info['name']} (PID: {proc.info['pid']})")
                                    proc.kill()

                            if killed_processes:
                                logging.critical(f"HEALTH CHECK: Successfully killed {len(killed_processes)} process(es): {', '.join(killed_processes)}")
                            else:
                                logging.critical("HEALTH CHECK: No matching game processes found to kill")

                        except Exception as e:
                            logging.critical(f"HEALTH CHECK: Failed to kill game process: {e}")
                        finally:
                            logging.critical("HEALTH CHECK: Process kill attempt completed")
                            logging.critical("=" * 60)

                # Check for recovery deadlock
                if (hasattr(serverstate, 'RECOVERY_IN_PROGRESS') and serverstate.RECOVERY_IN_PROGRESS and
                    hasattr(serverstate, 'LAST_RECOVERY_TIME') and serverstate.LAST_RECOVERY_TIME):

                    recovery_stuck_time = current_time - serverstate.LAST_RECOVERY_TIME
                    if recovery_stuck_time > 100:  # 100 seconds
                        logging.critical(f"HEALTH CHECK: Recovery deadlock detected ({recovery_stuck_time:.0f}s)")
                        try:
                            serverstate.reset_recovery_state()
                            serverstate.PAUSE_STATE = False
                            api.exec_command("map st1")
                            logging.critical("HEALTH CHECK: Forced emergency reset")
                        except Exception as e:
                            logging.critical(f"HEALTH CHECK: Emergency reset failed: {e}")

                # Check for general pause deadlock
                if (hasattr(serverstate, 'PAUSE_STATE') and serverstate.PAUSE_STATE and
                    hasattr(console, 'PAUSE_STATE_START_TIME') and console.PAUSE_STATE_START_TIME):

                    pause_stuck_time = current_time - console.PAUSE_STATE_START_TIME
                    if pause_stuck_time > 120:  # 2 minutes
                        logging.critical(f"HEALTH CHECK: Pause deadlock detected ({pause_stuck_time:.0f}s)")
                        try:
                            serverstate.PAUSE_STATE = False
                            api.exec_command("map st1")
                            logging.critical("HEALTH CHECK: Forced pause reset")
                        except Exception as e:
                            logging.critical(f"HEALTH CHECK: Pause reset failed: {e}")

        health_thread = threading.Thread(target=health_check_worker, daemon=True)
        health_thread.start()
        logging.info("Enhanced deadlock detection and game responsiveness health check started")

    # Call it once:
    add_periodic_health_check()

    while True:
        try:
            api.api_init()
            time.sleep(5)

            if not window_flag:
                logging.info("Found defrag window.")
                window_flag = True
                serverstate.PAUSE_STATE = False
                
                # NEW: Handle settings sync after unexpected crash recovery
                def handle_crash_recovery():
                    """Handle settings sync after unexpected game restart"""
                    import time
                    import websocket_console
                    
                    try:
                        # Wait for game to fully initialize before syncing
                        time.sleep(3)
                        
                        logging.info("Crash recovery: Syncing settings to VPS after unexpected restart")
                        
                        # Sync current settings to VPS (this will handle writeconfig internally)
                        websocket_console.sync_current_settings_to_vps()
                        logging.info("Crash recovery: Successfully synced settings to VPS")
                        
                    except Exception as e:
                        logging.error(f"Crash recovery: Failed to sync settings: {e}")
                
                # Run crash recovery in separate thread
                recovery_thread = threading.Thread(target=handle_crash_recovery)
                recovery_thread.daemon = True
                recovery_thread.start()
                
        except api.WindowNotFoundError:
            if not serverstate.VID_RESTARTING:
                window_flag = False
                logging.info("Defrag window lost. Restarting...")
                df_process = Process(target=launch)
                df_process.start()
                console.STOP_CONSOLE = True
                time.sleep(12)
                con_thread = threading.Thread(target=console.read, args=(logfile_path,), daemon=True)
                con_thread.start()