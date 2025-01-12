"""
This is the map data module
it allows us to save and load meta data related to each map
For now used to store data about gamma / reshade settings /  other visual stuff
But could be used in the future for any map specific data
"""

import sqlite3
import os.path
import json
import serverstate
import time
import api
import logging
from env import environ

STORAGE_PATH = environ['MAP_DATA']['STORAGE_PATH']
MAPDATA_TABLE = environ['MAP_DATA']['MAPDATA_TABLE']

SAVED_CMDS = {
    "angles": {
        "cmd": "df_chs1_Info6",
        "default": 0
    },
    "gamma": {
        "cmd": "r_gamma",
        "default": 1
    },
    "nodraw": {
        "cmd": "df_mp_NoDrawRadius",
        "default": 100
    },
    "drawgun": {
        "cmd": "cg_drawgun",
        "default": 1
    },
    "brightness": {
        "cmd": "r_mapoverbrightbits",
        "default": 2
    },
    "picmip": {
        "cmd": "r_picmip",
        "default": 0
    }
}


CURRENT_MAP = None


def singleton(c): return c()


@singleton
class MapData(object):
    def __init__(self):
        if not os.path.isfile(STORAGE_PATH):
            open(STORAGE_PATH, "x")

        con = sqlite3.connect(STORAGE_PATH)
        cur = con.cursor()

        # id (integer representing row id), mapname (string representing map name), data (json string that represents all data required)
        # we use json for data since it allows us to extra data for the future without having to change the database schema
        cur.execute(f"CREATE TABLE IF NOT EXISTS {MAPDATA_TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE, mapname TEXT, data TEXT)")
        con.commit()
        con.close()

    def load(self, mapname):
        con = sqlite3.connect(STORAGE_PATH)
        cur = con.cursor()
        result = cur.execute(f'SELECT * FROM {MAPDATA_TABLE} WHERE mapname = ? LIMIT 1', (mapname,)).fetchone()

        con.close()
        return result

    def save(self, mapname, key, value):
        con = sqlite3.connect(STORAGE_PATH)
        cur = con.cursor()
        result = self.load(mapname)

        if result is None:
            data = {
                key: value
            }

            cur.execute(f'INSERT INTO {MAPDATA_TABLE} (mapname, data) VALUES (?, ?)', (
                mapname,
                json.dumps(data)
            ))
        else:
            data = json.loads(result[2])
            data[key] = value

            cur.execute(f'UPDATE {MAPDATA_TABLE} SET data =  ? WHERE id = ?', (
                json.dumps(data),
                result[0]
            ))

        con.commit()
        con.close()

    # toggles key between value and default, if key doesn't exist, set it to value
    def toggle(self, mapname, key, value, default):
        result = self.load(mapname)

        save = value

        if result is not None:
            data = json.loads(result[2])
            if key in data and data[key] == value:
                save = default

        self.save(mapname, key, save)

    # remove specific key-value pair from data
    def clear(self, mapname, key):
        con = sqlite3.connect(STORAGE_PATH)
        cur = con.cursor()
        result = self.load(mapname)

        if result is None:
            return

        data = json.loads(result[2])
        data.pop(key, None)

        cur.execute(f'UPDATE {MAPDATA_TABLE} SET data =  ? WHERE id = ?', (
            json.dumps(data),
            result[0]
        ))
        con.commit()
        con.close()

    # delete all data related to a specific map
    def delete(self, mapname):
        con = sqlite3.connect(STORAGE_PATH)
        cur = con.cursor()
        cur.execute(f'DELETE FROM {MAPDATA_TABLE} WHERE mapname = ?', (mapname,))
        con.commit()
        con.close()


# mapdataHook is a hook that is used to check when map changes
# if it does, then it applies data from the database to the current map
def mapdataHook():
    global CURRENT_MAP
    while True:
        if serverstate.STATE.mapname != CURRENT_MAP and serverstate.STATE.mapname != None:
            CURRENT_MAP = serverstate.STATE.mapname
            logging.info("Map changed to : " + str(CURRENT_MAP))

            data = MapData.load(CURRENT_MAP)
            cmd = f"cg_centertime 3;displaymessage 140 10 Changing settings for map: {CURRENT_MAP}"

            if data is not None:
                data = json.loads(data[2])
                for key, value in SAVED_CMDS.items():
                    if key in data:
                        cmd += ";" + SAVED_CMDS[key]['cmd'] + " " + str(data[key])
                    else:
                        cmd += ";" + SAVED_CMDS[key]['cmd'] + " " + str(SAVED_CMDS[key]['default'])
            else:
                for key, value in SAVED_CMDS.items():
                    cmd += ";" + SAVED_CMDS[key]['cmd'] + " " + str(SAVED_CMDS[key]['default'])

            serverstate.VID_RESTARTING = True
            serverstate.PAUSE_STATE = True
            api.exec_command(cmd + "; vid_restart")

        time.sleep(4)
