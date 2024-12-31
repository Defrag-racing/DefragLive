import re
import os
from env import environ

DEVELOPMENT = environ["DEVELOPMENT"]
DF_EXE_PATH = environ["DF_EXE_PATH"]
DF_DIR = environ['DF_DIR']
CFG_NAME = environ['CFG_NAME']
CFG_P = os.path.join(DF_DIR, CFG_NAME)
DUMP_NAME = "condump.txt"
DUMP_P = os.path.join(DF_DIR, DUMP_NAME)
WS_ADDRESS = environ['WS_ADDRESS']

STATE_REPORT_P = os.path.join(DF_DIR, "system", "reports", environ["SVINFO_REPORT_NAME"])
INITIAL_REPORT_P = os.path.join(DF_DIR, "system", "reports", "initialstate.txt")

BINDS = None


def get_bind(cmd):
    global BINDS

    return BINDS[cmd]


def get_bind_fuzzy(rx, raw=False):
    global BINDS

    if not raw:
        rx = "^.*" + re.escape(rx) + ".*$"

    for cmd, bind in BINDS.items():
        if re.search(rx, cmd):
            return bind

    raise RuntimeError("Could not find bind for " + rx)


def read_cfg():
    global BINDS
    BINDS = {}

    with open(CFG_P, "r") as cfg_f:
        cfg = cfg_f.readlines()

    for line in cfg:
        try:
            r = r"bind[ ]+?(.+?)[ ]+?\"(.+?)\""
            match = re.match(r, line)
            key = match.group(1)
            cmd = match.group(2)
            BINDS[cmd] = key
        except:
            continue

    validate_cfg()


def validate_cfg():
    global BINDS

    # Replace all binds with their proper equivalents, if necessary
    BINDS["toggleconsole"] = 29

    for (cmd, bind) in BINDS.items():
        if cmd == "toggleconsole":
            continue
        elif re.match(r"^F\d+$", bind):
            BINDS[cmd] = "{" + bind + "}"
        elif bind == "ENTER":
            BINDS[cmd] = "{Enter}"
        elif bind == "ESCAPE":
            BINDS[cmd] = "{Esc}"
        elif bind == "TAB":
            BINDS[cmd] = "{Tab}"
        else:
            pass


def get_list(list):
    list_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lists', list)
    wordlist = []
    with open(list_path, "r") as list_file:
        for line in list_file:
            stripped_line = line.strip()
            if(stripped_line == ''): continue
            wordlist.append(stripped_line)
    return wordlist
