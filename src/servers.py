import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

LAST_SERVERS_DATA = None

def is_valid_ip(ip):
    servers_data = scrape_servers_data()

    if ip in servers_data['empty']:
        return {
            'status': False,
            'message': 'The server (' + ip + ') is empty. Try again later, or try to connect to a different server.' 
        }


    if ip in servers_data['active']:
        return {
            'status': True
        }

    return {
        'status': False,
        'message': 'The server (' + ip + ') is not whitelisted OR has not yet been registered as active.' 
    }

def scrape_servers_data():
    global LAST_SERVERS_DATA

    try:
        url = f'https://servers.defrag.racing/'
        data = requests.get(url, verify=False).json()
    except:
        return LAST_SERVERS_DATA or {
            "active": {},
            "empty": {}
        }

    LAST_SERVERS_DATA = data

    return data

def get_most_popular_server():
    """ Returns the IP of the server with the most players, or defrag.rocks if no servers are populated """
    servers_data = scrape_servers_data()

    servers_data = servers_data['active']

    max_plyr_qty = 0
    max_plyr_ip = ""

    for ip_addr, data in servers_data.items():
        active_players = get_active_players(data)
        player_qty = len(active_players)
        if player_qty > max_plyr_qty:
            max_plyr_qty = player_qty
            max_plyr_ip = ip_addr

    return max_plyr_ip

def get_least_popular_server():
    """ Returns the IP of the server with the least players, used only for development """
    servers_data = scrape_servers_data()

    servers_data = servers_data['active']

    min_plyr_qty = 9999
    min_plyr_ip = ""

    for ip_addr, data in servers_data.items():
        active_players = get_active_players(data)
        player_qty = len(active_players)
        if player_qty < min_plyr_qty:
            min_plyr_qty = player_qty
            min_plyr_ip = ip_addr

    return min_plyr_ip


def get_active_players(data):
    """Returns the amount of *active* players. Meaning player count without spectators or nospeccers"""
    speccable_players = []
    active_players = []
    if data['scores']['num_players']:
        if 'notice' in data:
            return data['scores']['players']

        for plyr_num in data['players']:
            print("plyr_num", plyr_num)
            player = data['players'][plyr_num]
            if not player['nospec']:
                speccable_players.append(int(player['clientId']))
        for score_player in data['scores']['players']:
            if score_player['player_num'] in speccable_players and score_player['follow_num'] == -1:
                active_players.append(score_player['player_num'])
    return active_players


def get_next_active_server(ignore_list, ignore_empty=False):
    """Returns the next active server omitting the servers given in ignore_list"""
    servers_data = scrape_servers_data()

    servers_data = servers_data['active']

    for ignore_ip in ignore_list:
        if ':' not in ignore_ip:
            ignore_ip += ':27960'

    max_plyr_qty = 0
    max_plyr_ip = ""

    for ip_addr, data in servers_data.items():
        active_players = get_active_players(data)
        player_qty = len(active_players)
        if player_qty > max_plyr_qty and ip_addr not in ignore_list:
            max_plyr_qty = player_qty
            max_plyr_ip = ip_addr

    print("Next active server: " + max_plyr_ip + " (" + str(max_plyr_qty) + " players)")

    if max_plyr_qty == 0 and ignore_empty:
        return None

    return max_plyr_ip
