"""This file contains all the handling logic for each twitchbot command available to DeFRaG players"""

import api
import requests
from env import environ
import serverstate
import logging
import time
import random

supported_commands = ["nospec", "info", "help", "howmany", "clear", "discord", "whoisthebest", "stonk", "f1", "f2", "spectate"]

# Spectate request messages - similar to serverstate.py greeting messages
SPECTATE_REQUEST_MESSAGES = [
    "please {PLAYERNAME} can we spectate your awesome skill in action?",
    "hey {PLAYERNAME}, would you mind sharing your epic gameplay with us?",
    "{PLAYERNAME}, we'd love to watch you dominate! Mind if we spectate?",
    "yo {PLAYERNAME}, can you show us how it's done? Please allow spectating!",
    "{PLAYERNAME}, your skills are legendary! Can we watch and learn?",
    "please {PLAYERNAME}, let us witness your mastery in action!",
    "{PLAYERNAME}, we're dying to see your techniques! Spectating please?",
    "hey {PLAYERNAME}, mind if we watch you work your magic?",
    "{PLAYERNAME}, share the knowledge! Can we spectate your run?",
    "please {PLAYERNAME}, let us learn from the master! Allow spectating?",
    "{PLAYERNAME}, the viewers are excited to see your moves!",
    "hey {PLAYERNAME}, would you consider letting us spectate your epic runs?",
    "{PLAYERNAME}, we promise to cheer you on if you let us watch!",
    "yo {PLAYERNAME}, the chat wants to see you in action! Spectating?",
    "{PLAYERNAME}, your gameplay is too good to miss! Can we watch?"
]

# Track spectate requests per player to prevent spam
SPECTATE_REQUESTS = {}  # player_name -> last_request_time
SPECTATE_COOLDOWN = 30  # 30 seconds between requests per player


def scan_for_command(message):
    """
    Scans a message content for a command
    :param message: The message content to scan
    :return: The command that has been called. None if no command found
    """
    for command in supported_commands:
        if message.startswith(f"?{command}"):
            return command
    return None


# The following are all the handler functions. They each take in line_data and return None

def handle_help(line_data):
    reply_string = "^7Current commands are ^3?^7nospec, ^3?^7info, ^3?^7help, ^3?^7clear, ^3?^7discord, ^3?^7howmany and ^3?^7spectate"
    api.exec_command(f"say {reply_string}")
    return None


def handle_nospec(line_data):
    api.exec_command(f"say ^7Don't want to be spectated? do ^3/color1 nospec^7, To allow spectating change it ^3/color1 specme")
    return None


def handle_whoisthebest(line_data):
    api.exec_command(f"varcommand say ^7You are the best $chsinfo(117). Only ^3you ^7and nobody else! ^1<3")
    return None


def handle_info(line_data):
    reply_string_1 = "^7This is a ^324/7 ^7livestream: ^3https://defrag.tv ^7| Contact: ^3defragtv@gmail.com."
    reply_string_2 = "^7Use ^3?^7help for a list of commands"
    api.exec_command(f"say {reply_string_1}")
    api.exec_command(f"say {reply_string_2}")
    return None


def handle_f1(line_data):
    if line_data["author"] not in serverstate.STATE.voter_names:
        logging.info(f'received f1 from {line_data["author"]}.')
        serverstate.STATE.voter_names.append(line_data["author"])
        serverstate.STATE.vy_count += 1


def handle_f2(line_data):
    if line_data["author"] not in serverstate.STATE.voter_names:
        logging.info(f'received f2 from {line_data["author"]}.')
        serverstate.STATE.voter_names.append(line_data["author"])
        serverstate.STATE.vn_count += 1


def handle_howmany(line_data):
    client_id = environ['TWITCH_API']['client_id']
    client_secret = environ['TWITCH_API']['client_secret']
    token_url = "https://id.twitch.tv/oauth2/token"
    token_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    r = requests.post(token_url, data=token_data, timeout=10)
    r.raise_for_status()
    token = r.json()['access_token']
    stream_url = f"https://api.twitch.tv/helix/streams?user_login={'defraglive'}"
    headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
    r = requests.get(stream_url, headers=headers, timeout=10)
    r.raise_for_status()
    stream_data = r.json()['data']
    viewer_count = stream_data[0]['viewer_count']
    reply_string = f"$chsinfo(117) ^7-- you are being watched by ^3{viewer_count} ^7viewer" + ("s" if viewer_count > 0 else "")
    api.exec_command(f"varcommand say {reply_string}")
    return None


def handle_clear(line_data):
    reply_string = "^7Ingame chat for viewers has been ^1erased."
    api.exec_command(f"clear; say {reply_string}")
    return None


def handle_discord(line_data):
    reply_string = "^7Join our discord: ^3https://discord.defrag.racing"
    api.exec_command(f"say {reply_string}")
    return None


def handle_spectate(line_data):
    """
    Handle spectate requests from players
    Usage: ?spectate <playername> - sends a polite request to the named player
           ?spectate - shows help message
    """
    global SPECTATE_REQUESTS, SPECTATE_COOLDOWN
    
    try:
        # Check if we have a player object passed from websocket handler
        target_player = None
        if 'target_player_obj' in line_data:
            target_player = line_data['target_player_obj']
            target_player_name = remove_color_codes(target_player.n)  # For display/logging
        else:
            # Parse the message to get the target player name (original behavior)
            message_parts = line_data['content'].split()
            
            if len(message_parts) < 2:
                # No target specified, show help
                api.exec_command("say ^7Usage: ^3?spectate <playername> ^7- send a polite spectate request")
                return None
            
            target_player_name = message_parts[1]
            
            # Check if we have a valid serverstate
            if not hasattr(serverstate, 'STATE') or serverstate.STATE is None:
                api.exec_command("say ^7Server state not available, try again later.")
                return None
            
            # Find the target player in the current server
            for player in serverstate.STATE.players:
                # Remove color codes for comparison
                clean_player_name = remove_color_codes(player.n).lower()
                clean_target_name = target_player_name.lower()
                
                if clean_player_name == clean_target_name or clean_target_name in clean_player_name:
                    target_player = player
                    break
        
        if not target_player:
            api.exec_command(f"say ^7Player '^3{target_player_name}^7' not found on this server.")
            return None
        
        # Check if player has nospec enabled
        if target_player.nospec != 1:
            api.exec_command(f"say ^3{target_player.n} ^7already allows spectating! Use the extension to spectate them.")
            return None
        
        requester = line_data["author"]
        current_time = time.time()
        
        # Get colored names from API
        colored_names = serverstate.get_colored_player_names()
        
        # Try to find colored version of player name
        clean_target_name = remove_color_codes(target_player.n).lower()
        colored_name = colored_names.get(clean_target_name, target_player.n)
        # Check cooldown for this specific player (use clean name for cooldown key)
        cooldown_key = f"{clean_target_name}_{requester}"
        if cooldown_key in SPECTATE_REQUESTS:
            time_since_last = current_time - SPECTATE_REQUESTS[cooldown_key]
            if time_since_last < SPECTATE_COOLDOWN:
                remaining_time = int(SPECTATE_COOLDOWN - time_since_last)
                api.exec_command(f"say ^3{requester}^7, please wait ^3{remaining_time}s ^7before requesting again.")
                return None
        
        # Update cooldown tracker
        SPECTATE_REQUESTS[cooldown_key] = current_time
        
        # Select random message and replace placeholder with colored name
        message_template = random.choice(SPECTATE_REQUEST_MESSAGES)
        spectate_message = message_template.replace('{PLAYERNAME}', f"{colored_name}^7")        
        # Send the request message with colored name
        api.exec_command(f"say ^3{requester} ^7asks: {spectate_message}")
        
        # Log the request (use clean name for logging clarity)
        logging.info(f"Spectate request sent by {requester} to {clean_target_name}: {spectate_message}")
        
        # Clean up old cooldown entries (prevent memory buildup)
        cleanup_old_requests(current_time)
        
    except Exception as e:
        logging.error(f"Error in handle_spectate: {e}")
        api.exec_command(f"say ^7Error processing spectate request. Try ^3?help ^7for available commands.")

def handle_stonk(line_data):
    try:
        line_list = line_data['content'].split()
        stonk = line_list[1]
        region = 'US'
        headers = {
            'x-rapidapi-key': environ['STONK_API']['key'],
            'x-rapidapi-host': environ['STONK_API']['host']
        }
        url = "https://apidojo-yahoo-finance-v1.p.rapidapi.com/auto-complete"
        querystring = {"q": stonk, "region": region}
        response = requests.request("GET", url, headers=headers, params=querystring)
        symbol = response.json()['quotes'][0]['symbol']

        url = "https://apidojo-yahoo-finance-v1.p.rapidapi.com/stock/v2/get-summary"
        querystring = {"symbol": symbol, "region": region}
        response = requests.request("GET", url, headers=headers, params=querystring)
        short_name, symbol, exchange = [response.json()['quoteType'][i] for i in ('shortName', 'symbol', 'exchange')]
        price, change = [response.json()['price'][i]['fmt'] for i in ('regularMarketPrice', 'regularMarketChangePercent')]
        currency = response.json()['price']['currency']
        color = "^1" if '-' in change else "^2"
        change = change.replace('%', ' p/c')
        reply_string = f"^7{symbol}^3: {color}{price} {currency} ({change}) ^7{short_name} ({exchange})"
    except Exception as e:
        logging.error(f"Error in stonk command: {e}")
        reply_string = "Invalid input. Usage: ?stonk <symbol>"
    return api.exec_command(f"say {reply_string}")


def remove_color_codes(text):
    """Remove Quake 3 color codes from text for comparison"""
    import re
    return re.sub(r'\^.', '', text)


def cleanup_old_requests(current_time):
    """Clean up old spectate request entries to prevent memory buildup"""
    global SPECTATE_REQUESTS, SPECTATE_COOLDOWN
    
    keys_to_remove = []
    for key, timestamp in SPECTATE_REQUESTS.items():
        if current_time - timestamp > SPECTATE_COOLDOWN * 2:  # Clean up entries older than 2x cooldown
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del SPECTATE_REQUESTS[key]