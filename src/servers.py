import requests
from bs4 import BeautifulSoup

def scrape_servers_data():
    """ Obtains data from q3df.org/servers using web scraping"""
    url = f'https://servers.defrag.racing/'
    data = requests.get(url, verify=False).json()

    print(data)

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
        for plyr_num in data['players']:
            player = data['players'][plyr_num]
            if not player['nospec']:
                speccable_players.append(int(player['clientId']))
        for score_player in data['scores']['players']:
            if score_player['player_num'] in speccable_players and score_player['follow_num'] == -1:
                active_players.append(score_player['player_num'])
    return active_players


def get_next_active_server(ignore_list):
    """Returns the next active server omitting the servers given in ignore_list"""
    servers_data = scrape_servers_data()

    # print(str(servers_data))

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

    return max_plyr_ip
