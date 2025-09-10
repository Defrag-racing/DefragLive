from env import environ
import asyncio
import websockets
import logging
import time
import json
import random

import api
import console
import config
import serverstate
import filters
import servers

import requests
import threading

# logger = logging.getLogger('websockets')
# logger.setLevel(logging.DEBUG)
# logger.addHandler(logging.StreamHandler())

import os
import time
import logging

SETTINGS_QUEUE = []
CANCEL_PENDING_WRITECONFIG = False

def handle_settings_command(content):
    """Handle settings command from VPS"""
    # QUEUE SETTINGS COMMANDS DURING MAP LOADING
    if hasattr(serverstate, 'PAUSE_STATE') and serverstate.PAUSE_STATE:
        logging.info(f"[SETTINGS] Queued settings command during pause: {content['command']}")
        SETTINGS_QUEUE.append(content)
        return
        
    if hasattr(serverstate, 'CONNECTING') and serverstate.CONNECTING:
        logging.info(f"[SETTINGS] Queued settings command during connecting: {content['command']}")
        SETTINGS_QUEUE.append(content)
        return
    
    # Execute immediately if not loading
    execute_settings_command(content)

def execute_settings_command(content):
    global CANCEL_PENDING_WRITECONFIG
    
    logging.info(f'[SETTINGS] Received command: {content["command"]}')
    
    try:
        command = content["command"]
        
        if command == "vid_restart":
            logging.info("[SETTINGS] Executing vid_restart - canceling any pending writeconfig")
            CANCEL_PENDING_WRITECONFIG = True  # Cancel any pending writeconfig
            import serverstate
            serverstate.VID_RESTARTING = True
            serverstate.PAUSE_STATE = True
            api.exec_command(command)
            logging.info(f'[SETTINGS] Executed: {command}')
            return
        
        # RESET flag for regular commands
        CANCEL_PENDING_WRITECONFIG = False
        
        # Add seta prefix only for extension cvars if not already present
        extension_cvars = [
            'r_renderTriggerBrushes', 'r_fastsky', 'r_renderClipBrushes', 'r_renderSlickSurfaces',
            'r_mapOverbrightBits', 'r_picmip', 'r_fullbright', 'r_gamma', 'cg_drawGun',
            'df_chs1_Info6', 'cg_lagometer', 'mdd_snap', 'mdd_cgaz', 'df_chs1_Info5',
            'df_drawSpeed', 'df_chs0_Draw', 'df_chs1_Info7', 'df_mp_NoDrawRadius',
            'cg_thirdperson', 'df_ghosts_MiniviewDraw', 'cg_gibs', 'com_blood'
        ]
        
        # Check if command starts with any of the extension cvars and add seta if needed
        for cvar in extension_cvars:
            if command.startswith(f"{cvar} ") and not command.startswith("seta "):
                command = f"seta {command}"
                logging.info(f'[SETTINGS] Modified extension command to use seta: {command}')
                break
        
        # Execute the setting command
        api.exec_command(command)
        logging.info(f'[SETTINGS] Executed: {command}')
        
        # Add 1-second delay before writeconfig for non-vid_restart commands
        def delayed_writeconfig():
            import time
            global CANCEL_PENDING_WRITECONFIG
            time.sleep(1)
            # Check if writeconfig was cancelled
            if not CANCEL_PENDING_WRITECONFIG:
                api.exec_command("writeconfig settings-current.cfg")
                logging.info("[SETTINGS] Wrote config after 1-second delay")
                
                # Sync settings after writeconfig for regular commands
                def delayed_settings_confirmation():
                    import time
                    time.sleep(1)  # Wait for writeconfig to complete
                    try:
                        sync_current_settings_to_vps()
                        logging.info("[SETTINGS] Synced settings after regular command")
                    except Exception as e:
                        logging.error(f"[SETTINGS] Failed to sync after regular command: {e}")
                
                import threading
                sync_thread = threading.Thread(target=delayed_settings_confirmation)
                sync_thread.daemon = True
                sync_thread.start()
            else:
                logging.info("[SETTINGS] Writeconfig cancelled due to vid_restart")
        
        # Start the writeconfig thread
        import threading
        writeconfig_thread = threading.Thread(target=delayed_writeconfig)
        writeconfig_thread.daemon = True
        writeconfig_thread.start()
        
    except Exception as e:
        logging.error(f'[SETTINGS] Failed to execute command {content["command"]}: {e}')

def process_queued_settings():
    """Process all queued settings commands after map loading"""
    global SETTINGS_QUEUE
    
    if SETTINGS_QUEUE:
        logging.info(f"[SETTINGS] Processing {len(SETTINGS_QUEUE)} queued settings commands")
        
        for content in SETTINGS_QUEUE:
            execute_settings_command(content)
        
        SETTINGS_QUEUE.clear()
        logging.info("[SETTINGS] Finished processing queued settings commands")
        
        # NEW: Sync settings after processing all queued commands
        import threading
        def delayed_queue_sync():
            import time
            time.sleep(1)  # Wait for all commands to take effect
            try:
                sync_current_settings_to_vps()
                logging.info("[SETTINGS] Synced settings after processing queued commands")
            except Exception as e:
                logging.error(f"[SETTINGS] Failed to sync after queue processing: {e}")
        
        sync_thread = threading.Thread(target=delayed_queue_sync)
        sync_thread.daemon = True
        sync_thread.start()

def get_current_game_settings():
    """Get current game settings by reading the config file"""
    settings_file_path = r"D:\Games\defragtv\defrag\settings-current.cfg"
    
    # Default values for all cvars
    default_values = {
        'r_renderTriggerBrushes': '0',
        'r_fastsky': '0', 
        'r_renderClipBrushes': '0',
        'r_renderSlickSurfaces': '0',
        'r_mapOverbrightBits': '2',
        'r_picmip': '0',
        'r_fullbright': '0',
        'r_gamma': '1.2',
        'cg_drawGun': '1',
        'df_chs1_Info6': '0',
        'cg_lagometer': '0',
        'mdd_snap': '3',
        'mdd_cgaz': '1',
        'df_chs1_Info5': '23',
        'df_drawSpeed': '0',
        'df_chs0_Draw': '1',
        'df_chs1_Info7': '0',
        'df_mp_NoDrawRadius': '100',
        'cg_thirdperson': '0',
        'df_ghosts_MiniviewDraw': '0',
        'cg_gibs': '0',
        'com_blood': '0'
    }
    
    # Mapping from game cvars to UI setting names
    cvar_to_setting = {
        'r_renderTriggerBrushes': 'triggers',
        'r_fastsky': 'sky',
        'r_renderClipBrushes': 'clips', 
        'r_renderSlickSurfaces': 'slick',
        'r_mapOverbrightBits': 'brightness',
        'r_picmip': 'picmip',
        'r_fullbright': 'fullbright',
        'r_gamma': 'gamma',
        'cg_drawGun': 'drawgun',
        'df_chs1_Info6': 'angles',
        'cg_lagometer': 'lagometer',
        'mdd_snap': 'snaps',
        'mdd_cgaz': 'cgaz',
        'df_chs1_Info5': 'speedinfo',
        'df_drawSpeed': 'speedorig',
        'df_chs0_Draw': 'inputs',
        'df_chs1_Info7': 'obs',
        'df_mp_NoDrawRadius': 'nodraw',
        'cg_thirdperson': 'thirdperson',
        'df_ghosts_MiniviewDraw': 'miniview',
        'cg_gibs': 'gibs',
        'com_blood': 'blood'
    }
    
    try:
        # Execute writeconfig command to generate current settings file
        logging.info("[SETTINGS] Writing current config to settings-current.cfg")
        api.exec_command("writeconfig settings-current.cfg")
        
        # Wait for file to be written
        time.sleep(0.5)
        
        # Check if file exists
        if not os.path.exists(settings_file_path):
            logging.error(f"[SETTINGS] Config file not found: {settings_file_path}")
            return {}
        
        # Read the config file and parse cvar values
        current_values = {}
        
        with open(settings_file_path, 'r') as f:
            content = f.read()
            
        # Parse each line to find cvar settings
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('//') or line.startswith('#'):
                continue
                
            # Look for "seta cvar_name value" format
            if line.startswith('seta '):
                parts = line.split()
                if len(parts) >= 3:
                    cvar_name = parts[1]
                    cvar_value = parts[2].strip('"')  # Remove quotes if present
                    
                    # Case-insensitive lookup
                    for default_cvar in default_values.keys():
                        if cvar_name.lower() == default_cvar.lower():
                            current_values[default_cvar] = cvar_value
                            break
        
        # Fill in missing cvars with defaults
        for cvar_name in default_values:
            if cvar_name not in current_values:
                current_values[cvar_name] = default_values[cvar_name]
                logging.info(f"[SETTINGS] Using default value for {cvar_name}: {default_values[cvar_name]}")
        
        # Convert to UI setting format
        ui_settings = {}
        for cvar_name, cvar_value in current_values.items():
            if cvar_name in cvar_to_setting:
                setting_key = cvar_to_setting[cvar_name]
                
                # Convert to UI setting format
                ui_settings = {}
                for cvar_name, cvar_value in current_values.items():
                    if cvar_name in cvar_to_setting:
                        setting_key = cvar_to_setting[cvar_name]
                        
                        # Convert values to appropriate types
                        if setting_key in ['brightness', 'picmip']:
                            # Integer values that stay as integers
                            ui_settings[setting_key] = int(cvar_value)
                        elif setting_key == 'gamma':
                            # Float value
                            ui_settings[setting_key] = float(cvar_value)
                        elif setting_key == 'drawgun':
                            # 1 = True, 2 = False
                            ui_settings[setting_key] = (int(cvar_value) == 1)
                        elif setting_key == 'sky':
                            # 0 = True, 1 = False (reversed!)
                            ui_settings[setting_key] = (int(cvar_value) == 0)
                        elif setting_key == 'angles':
                            # 40 = True, 0 = False
                            ui_settings[setting_key] = (int(cvar_value) == 40)
                        elif setting_key == 'snaps':
                            # 3 = True, 0 = False - send as boolean
                            ui_settings[setting_key] = (int(cvar_value) == 3)
                        elif setting_key == 'speedinfo':
                            # 23 = True, 0 = False - send as boolean
                            ui_settings[setting_key] = (int(cvar_value) == 23)
                        elif setting_key == 'obs':
                            # 50 = True, 0 = False - send as boolean
                            ui_settings[setting_key] = (int(cvar_value) == 50)
                        elif setting_key == 'nodraw':
                            # 100000 = True, 100 = False - send as boolean
                            ui_settings[setting_key] = (int(cvar_value) == 100000)
                        else:
                            # Standard boolean values (0 = False, anything else = True)
                            ui_settings[setting_key] = bool(int(cvar_value))
        
        logging.info(f"[SETTINGS] Successfully read current game settings: {ui_settings}")
        return ui_settings
        
    except Exception as e:
        logging.error(f"[SETTINGS] Failed to get current game settings: {e}")
        return {}

def sync_current_settings_to_vps():
    """Send current game settings to VPS when bot starts"""
    logging.info("[SETTINGS] Syncing current game settings to VPS")
    
    try:
        current_settings = get_current_game_settings()
        
        if current_settings:
            # Send to VPS - use 'sync_settings' to match what VPS bridge expects
            sync_message = {
                'action': 'sync_settings',  # VPS bridge expects this action name
                'settings': current_settings,
                'source': 'defrag_bot'
            }
            
            console.WS_Q.put(json.dumps(sync_message))
            logging.info(f"[SETTINGS] Sent current settings to VPS: {current_settings}")
        else:
            logging.warning("[SETTINGS] No settings to sync")
        
    except Exception as e:
        logging.error(f"[SETTINGS] Failed to sync settings to VPS: {e}")

def serverstate_to_json():
    data = {
        'bot_id': serverstate.STATE.bot_id,
        'bot_secret': serverstate.STATE.secret,
        'current_player_id': serverstate.STATE.current_player_id,
        'mapname': serverstate.STATE.mapname,
        'df_promode': serverstate.STATE.df_promode,
        'defrag_gametype': serverstate.STATE.defrag_gametype,
        'num_players': serverstate.STATE.num_players,
        'ip': serverstate.STATE.ip,
        'hostname': serverstate.STATE.hostname,
        'players': {},
    }

    if serverstate.STATE.current_player is not None:
        data['current_player'] = serverstate.STATE.current_player.__dict__

        if 'n' in data['current_player']:
            data['current_player']['n'] = filters.filter_author(data['current_player']['n'])
    else:
        data['current_player'] = None  # ADD THIS LINE - explicitly set to None

    for pl in serverstate.STATE.players:
        pl_dict = pl.__dict__

        if 'n' in pl_dict:
            pl_dict['n'] = filters.filter_author(pl_dict['n'])

        data['players'][pl_dict['id']] = pl_dict

    return data

# ------------------------------------------------------------
# - Flask API for the twitch extension
# ------------------------------------------------------------

from flask import Flask, jsonify
app = Flask(__name__)


@app.route('/serverstate.json')
def parsed_serverstate():
    data = serverstate_to_json()
    output = jsonify(data)

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


@app.route('/console.json')
def parsed_console_log():
    output = console.CONSOLE_DISPLAY[-200:] # [::-1] = reversed. console needs new messages at bottom
    output = jsonify(output)

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


@app.route('/console/raw.json')
def raw_console_log():
    output = console.LOG[::-1]
    output = jsonify(output)

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


@app.route('/console/delete_message/<id>')
def delete_message(id):
    output = jsonify({'status': 'ok'})

    for idx, msg in enumerate(console.CONSOLE_DISPLAY):
        if msg['id'] == id:
            del console.CONSOLE_DISPLAY[idx]
            break

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


# ASGI server
def run_flask_server(host, port):
    import uvicorn
    import asgiref.wsgi

    asgi_app = asgiref.wsgi.WsgiToAsgi(app)
    uvicorn.run(asgi_app, host=host, port=port, log_level="warning", access_log=False)


# ------------------------------------------------------------
# - Websocket client
# ------------------------------------------------------------

def notify_serverstate_change():
    data = serverstate_to_json()

    console.WS_Q.put(json.dumps({'action': 'serverstate', 'message': data}))
    logging.info('--- serverstate change ---')

def handle_ws_command(msg):
    logging.info('[WS] Handle command: %s', str(msg))

    content = msg['message']['content']
    author = 'Guest'
    if 'author' in msg['message']:
        author = msg['message']['author'] if msg['message']['author'] is not None else 'Guest'
    if type(content) is not dict:
        return

    if content['action'] == 'translate_message':
        cache_key = content['cache_key']
        text = content['text'] 
        message_id = content.get('message_id')
        
        logging.info(f"[TRANSLATION REQUEST] Cache key: {cache_key[:50]}...")
        handle_translation_request(cache_key, text, message_id)
        return

    # In websocket_console.py, modify the handle_ws_command function:

    if content['action'] == 'spectate':
        logging.info("[CONSOLE] SPECTATE REQUEST")

        if content['value'] == 'next':
            serverstate.switch_spec('next')
            api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3{author} ^7has switched to ^3 Next Player")
            time.sleep(1)
            return
        if 'id:' in content['value']:
            id = content['value'].split(':')[1]
            logging.info("[CONSOLE] SPECIFIC ID SPECTATE REQUEST " + str(id))
            
            # MANUAL SPECTATE - Reset AFK state for the selected player
            if hasattr(serverstate, 'STATE') and serverstate.STATE:
                # Remove the selected player from AFK list if they were there
                if id in serverstate.STATE.afk_ids:
                    serverstate.STATE.afk_ids.remove(id)
                    logging.info(f"Removed player {id} from AFK list due to manual spectate")
                
                # Reset AFK counter since this is a manual override
                serverstate.STATE.afk_counter = 0
                
                # Clear IGNORE_IPS to allow staying on current server
                serverstate.IGNORE_IPS = []
                
                # Reset any custom AFK timeout for this player back to default
                if str(id) in serverstate.STATE.player_afk_timeouts:
                    del serverstate.STATE.player_afk_timeouts[str(id)]
                    logging.info(f"Reset AFK timeout for player {id} back to default (manual spectate)")
                    
                logging.info(f"Manual spectate to {id}: AFK counter reset, player removed from AFK list")
            
                api.exec_command(f"follow {id}")
                serverstate.STATE.current_player_id = int(id)  # Convert to int for consistency
                serverstate.STATE.current_player = serverstate.STATE.get_player_by_id(int(id))
                api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3{author} ^7has switched to ^3 Next Player")

    if content['action'] == 'spectate_request':
        player_name = content['value']
        logging.info(f"[CONSOLE] SPECTATE REQUEST for player: {player_name}")
        
        # Find the original player object with color codes intact
        target_player = None
        if hasattr(serverstate, 'STATE') and serverstate.STATE is not None:
            for player in serverstate.STATE.players:
                # Remove color codes for comparison
                clean_player_name = remove_color_codes(player.n).lower()
                clean_target_name = remove_color_codes(player_name).lower()
                
                if clean_player_name == clean_target_name or clean_target_name in clean_player_name:
                    target_player = player
                    break
        
        if target_player:
            # Use the original name with colors instead of the filtered one from extension
            original_name_with_colors = target_player.n            
            # Create a fake line_data structure but use original name
            fake_line_data = {
                'author': author,
                'content': f"?spectate {original_name_with_colors}",
                'type': 'EXT_COMMAND',
                'target_player_obj': target_player  # Pass the actual player object
            }
        else:
            # Fallback to original behavior if player not found
            fake_line_data = {
                'author': author,
                'content': f"?spectate {player_name}",
                'type': 'EXT_COMMAND'
            }
        
        # Import and call the spectate handler
        import dfcommands
        dfcommands.handle_spectate(fake_line_data)
        return

    if content['action'] == 'connect':
        ip = content['value']
        logging.info(f"[CONSOLE] CONNECT REQUEST to {ip}")

        # Validate IP (consistent with twitch_commands.py)
        result = servers.is_valid_ip(ip)
        if not result['status']:
            msg = result['message']
            api.exec_command(f"cg_centertime 5;varcommand displaymessage 140 8 ^3{author} ^1{msg};")
            logging.info(msg)
            # Optionally send error back to extension via websocket (e.g., for UI feedback)
            console.WS_Q.put(json.dumps({
                'action': 'connect_error',
                'message': msg
            }))
            return

        # Proceed with connection
        api.exec_command("say ^7Switching servers. ^3Farewell.")
        
        # Wait 2 seconds before connecting to new server
        time.sleep(2)
        
        serverstate.RECONNECTED_CHECK = True
        serverstate.connect(ip, author)
        # Optionally send success back to extension
        console.WS_Q.put(json.dumps({
            'action': 'connect_success',
            'message': f"Connecting to {ip}"
        }))
        return

    if content['action'] == 'afk_control':
        command = content['command']  # 'reset' or 'extend'
        logging.info(f"[CONSOLE] AFK CONTROL REQUEST: {command}")
        
        # Import the afk function from twitch_commands to reuse the logic
        import twitch_commands
        import asyncio
        
        # Create a mock context object for the async function
        class MockContext:
            class MockChannel:
                async def send(self, message):
                    pass  # Do nothing - we don't want Twitch chat output from buttons
            channel = MockChannel()
        
        # Call the existing afk function with the appropriate arguments
        mock_ctx = MockContext()
        args = [command] if command in ['reset', 'extend'] else []
        
        # Run the async function in a thread to avoid blocking
        import threading
        def run_afk_command():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(twitch_commands.afk(mock_ctx, author, args))
            except Exception as e:
                logging.error(f"Error running AFK command: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_afk_command)
        thread.daemon = True
        thread.start()
        
        return


def remove_color_codes(text):
    """Remove Quake 3 color codes from text for comparison"""
    import re
    return re.sub(r'\^.', '', text)

def on_ws_message(msg):
    message = {}

    if msg is None:
        return

    try:
        message = json.loads(msg)
    except Exception as e:
        logging.info('ERROR [on_ws_message]:', e)
        return

    # Handle settings commands from VPS (BEFORE origin check)
    if message.get('action') == 'execute_command':
        handle_settings_command(message)
        return

    # if there is no origin, exit
    # this function only processes messages directly from twitch console extension
    if 'origin' not in message:
        return
    if message['origin'] != 'twitch':
        return

    if 'message' in message:
        if message['message'] is None:
            message['message'] = {}

        # Handle actions from twitch extension
        if message['action'] == 'ext_command':
            handle_ws_command(message)
            return

        # Ignore serverstate messages
        if message['action'] == 'serverstate':
            return

        message_text = message['message']['content']

        if ";" in message_text:  # prevent q3 command injections
            message_text = message_text[:message_text.index(";")]

        if message_text.startswith("!"):  # proxy mod commands (!top, !rank, etc.)
            # BLOCK PROXY COMMANDS DURING MAP LOADING
            if hasattr(serverstate, 'PAUSE_STATE') and serverstate.PAUSE_STATE:
                logging.info(f"Blocked proxy command during pause: {message_text}")
                return
                
            if hasattr(serverstate, 'CONNECTING') and serverstate.CONNECTING:
                logging.info(f"Blocked proxy command during connecting: {message_text}")
                return
                
            logging.info("proxy command received")
            api.exec_command(message_text)
            time.sleep(1)
        else:
            # BLOCK CHAT MESSAGES DURING MAP LOADING
            if hasattr(serverstate, 'PAUSE_STATE') and serverstate.PAUSE_STATE:
                logging.info(f"Blocked websocket chat message during pause: {message_text}")
                return
                
            if hasattr(serverstate, 'CONNECTING') and serverstate.CONNECTING:
                logging.info(f"Blocked websocket chat message during connecting: {message_text}")
                return
                
            author = 'Guest'
            if 'author' in message['message']:
                author = message['message']['author']
            author += ' ^7> '
            author_color_num = min(ord(author[0].lower()), 9) # replace ^[a-z] with ^[0-9]
            message_content = message_text.lstrip('>').lstrip('<')
            api.exec_command(f"say ^{author_color_num}{author} ^2{message_content}")


async def ws_send_queue(websocket, q):
    last_ping = time.time()
    ping_interval = 30  # Send ping every 30 seconds
    
    while True:
        try:
            # Check if we need to send a keepalive ping
            current_time = time.time()
            if current_time - last_ping >= ping_interval:
                try:
                    pong_waiter = await websocket.ping()
                    await asyncio.wait_for(pong_waiter, timeout=10)  # 10 second timeout for pong response
                    last_ping = current_time
                    console.update_websocket_health()
                    logging.debug("Websocket keepalive ping successful")
                except asyncio.TimeoutError:
                    logging.error("Websocket keepalive pong timeout")
                    raise websockets.exceptions.ConnectionClosedError(1011, "keepalive ping timeout")
                except Exception as e:
                    logging.error(f"Websocket keepalive ping failed: {e}")
                    raise
            
            if not q.empty():
                msg = q.get()
                # logging.info('ws_send_queue msg: {}'.format(msg))
                if msg == '>>quit<<':
                    await websocket.close(reason='KTHXBYE!')
                    break
                else:
                    await websocket.send(msg)
                    console.update_websocket_health()
            else:
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
        except Exception as e:
            logging.error(f"Error in ws_send_queue: {e}")
            raise


async def ws_receive(websocket):
    try:
        async for msg in websocket:
            # logging.info('ws_receive msg: {}'.format(msg))
            on_ws_message(msg)
            console.update_websocket_health()  # Update health when receiving messages
    except websockets.exceptions.ConnectionClosed as e:
        logging.error(f"Websocket connection closed: {e}")
        raise
    except Exception as e:
        logging.error(f"Error in ws_receive: {e}")
        raise


async def ws_start(q):
    try:
        async with websockets.connect(config.WS_ADDRESS, ping_interval=None) as websocket:
            # Identify this connection as the DefragLive bot
            bot_id_message = {
                'action': 'identify_bot'
            }
            await websocket.send(json.dumps(bot_id_message))
            logging.info("[SETTINGS] Identified as DefragLive bot to VPS")
            logging.info("Websocket connection established successfully")
            
            # Sync current settings to VPS after connecting
            sync_current_settings_to_vps()
            
            await asyncio.gather(
                ws_receive(websocket),
                ws_send_queue(websocket, q),
            )
    except websockets.exceptions.ConnectionClosed as e:
        logging.error(f"Websocket connection closed during startup: {e}")
        raise
    except Exception as e:
        logging.error(f"Error in ws_start: {e}")
        raise

def ws_worker(q, loop):
    reconnect_delay = 1  # Start with 1 second
    max_delay = 30       # Max 30 seconds between attempts
    consecutive_failures = 0
    connection_successful = False
    
    while True:
        try:
            logging.info("Attempting websocket connection...")
            loop.run_until_complete(ws_start(q))
            # If we get here, connection was successful, reset counters
            reconnect_delay = 1
            consecutive_failures = 0
            connection_successful = True
            console.update_websocket_health()  # Update health on successful connection
            logging.info("Websocket connection established successfully")
            
        except Exception as e:
            consecutive_failures += 1
            connection_successful = False
            error_str = str(e)
            
            # Special handling for keepalive ping timeouts
            if "keepalive ping timeout" in error_str or "1011" in error_str:
                logging.error(f'Websocket connection failed (attempt {consecutive_failures}): received 1011 (internal error) keepalive ping timeout; then sent 1011 (internal error) keepalive ping timeout')
            else:
                logging.warning(f'Websocket connection failed (attempt {consecutive_failures}): {error_str}')
            
            # Send error notification to extension
            try:
                error_msg = {
                    'id': console.message_to_id(f"WS_ERROR_{time.time()}"),
                    'type': 'CONNECTION_ERROR',
                    'author': None,
                    'content': f'Websocket connection failed: {error_str} (attempt {consecutive_failures})',
                    'timestamp': time.time(),
                    'command': None
                }
                console.WS_Q.put(json.dumps({'action': 'message', 'message': error_msg}))
            except Exception as queue_error:
                logging.error(f"Failed to send websocket error to extension: {queue_error}")
            
            # Exponential backoff with jitter
            if consecutive_failures <= 3:
                # First few attempts: quick retry
                delay = reconnect_delay
            else:
                # After multiple failures: exponential backoff
                delay = min(max_delay, reconnect_delay * (2 ** min(consecutive_failures - 3, 4)))
            
            # Add small random jitter to prevent thundering herd
            jitter = random.uniform(0.1, 0.3)
            total_delay = delay + jitter
            
            logging.info(f'Retrying websocket connection in {total_delay:.1f} seconds...')
            time.sleep(total_delay)