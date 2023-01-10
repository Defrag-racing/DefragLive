import requests
from bs4 import BeautifulSoup

HOSTNAMES = {
    "defrag.rocks": "140.82.4.154",
    "q3df.ru": "83.243.73.220",
    "au.q3df.run": "54.206.0.6",
    "se.q3df.run": "13.51.137.1",
    "sg.q3df.run": "175.41.167.174",
    "br.q3df.run": "54.94.102.4",
    "jp.q3df.run": "35.72.202.141",
    "gb.q3df.run": "3.10.114.224",
    "us.q3df.run": "52.39.193.224",
    "za.q3df.run": "13.245.107.109",
    "cl.q3df.run": "186.64.123.196",
    "cn.q3df.run": "101.132.103.203",
    "ca.q3df.run": "35.183.79.73",
    "localhost": "127.0.0.1",
    "PC": "192.168.1.22",
}


def scrape_servers_data():
    """ Obtains data from q3df.org/servers using web scraping"""
    url = f'https://servers.q3df.run/'
    data = requests.get(url, verify=False).json()
    return data


def check_if_valid_ip(ip: str):
    """
    Checks whether or not a given IP is listed on q3df.org/servers
    :param ip: The IP to validate
    :return: True or False
    """
    servers_data = scrape_servers_data()

    return len([server for (id, server) in servers_data.items() if ip == server["state"]["ip"]]) > 0


def apply_whitelist(servers_data):
    """
    Applies the server ip whitelist to current server data object
    :param servers_data:
    :return:
    """
    from config import get_list
    filtered_server_data = dict()
    for sv_ip, sv_data in servers_data['active'].items():
        if sv_ip.split(':')[0] in get_list('whitelist_servers'):
            filtered_server_data[sv_ip] = sv_data
    return filtered_server_data


def get_most_popular_server():
    """ Returns the IP of the server with the most players, or defrag.rocks if no servers are populated """
    servers_data = scrape_servers_data()

    servers_data = apply_whitelist(servers_data)

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

    servers_data = apply_whitelist(servers_data)

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
    from config import get_list
    servers_data = scrape_servers_data()
    print(str(servers_data))
    servers_data = apply_whitelist(servers_data)

    for ignore_ip in ignore_list:
        ignore_ip = resolve_hostname(ignore_ip)
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


def resolve_hostname(ip):
    for hostname in HOSTNAMES:
        if hostname in ip:
            new_ip = ip.replace(hostname, HOSTNAMES[hostname])
            print("resolved {ip} to {new_ip}")
            return new_ip
    return ip
