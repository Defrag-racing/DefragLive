"""This file contains all the handling logic for each twitchbot command available to DeFRaG players"""

import api
import requests
from env import environ
import serverstate
import logging
supported_commands = ["nospec", "info", "help", "howmany", "clear", "discord", "whoisthebest", "stonk", "f1", "f2"]


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
    reply_string = "^7Current commands are ^3?^7nospec, ^3?^7info, ^3?^7help, ^3?^7clear, ^3?^7discord and ^3?^7howmany"
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
    token_url = f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
    r = requests.post(token_url)
    token = r.json()['access_token']
    stream_url = f"https://api.twitch.tv/helix/streams?user_login={'defraglive'}"
    headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
    r = requests.get(stream_url, headers=headers)
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
    except:
        reply_string = "Invalid input. Usage: ?stonk <symbol>"
    return api.exec_command(f"say {reply_string}")
