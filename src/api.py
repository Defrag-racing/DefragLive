import os
import time
from env import environ
import logging

from ahk import AHK

import config


AHK = AHK()
CONSOLEWINDOW = "TwitchBot Console"
ENGINEWINDOW = "TwitchBot Engine"

# delay between sounds, used to prevent overlapping sounds
# could be set to zero if u don't care about sound overlapping
# (maybe viewer should be able to spam holy or 4ity or whatever)
SOUND_DELAY = 1
SOUND_TIMER = 0.0


class WindowNotFoundError(Exception):
    pass


def api_init():
    """Grab both engine and console windows. Thanks to run for this code"""
    global CONSOLE
    global WINDOW

    if environ["DEVELOPMENT"]:
        CONSOLE = AHK.run_script("WinShow," + CONSOLEWINDOW +
                   "\nControlGet, console, Hwnd ,, Edit1, " + CONSOLEWINDOW +
                   "\nFileAppend, %console%, * ;", blocking=True)
    else:
        CONSOLE = AHK.run_script("WinShow," + CONSOLEWINDOW + \
                    "\nControlGet, console, Hwnd ,, Edit1, " + CONSOLEWINDOW +
                    "\nWinHide," + CONSOLEWINDOW +
                    "\nFileAppend, %console%, * ;", blocking=True)
    WINDOW = AHK.find_window(process=config.DF_EXE_PATH, title=b"TwitchBot Engine")

    if CONSOLE is None or WINDOW is None:
        raise WindowNotFoundError


def exec_command(cmd, verbose=True):
    if verbose:
        logging.info(f"Execing command {cmd}")
    # send the text to the console window, escape commas (must be `, to show up in chat)
    AHK.run_script("ControlSetText, , " + cmd.replace(',', '`,') + ", ahk_id " + CONSOLE +
                "\nControlSend, , {Enter}, ahk_id " + CONSOLE, blocking=True)


def play_sound(sound):
    if not os.path.exists(environ['DF_DIR'] + f"music\\common\\{sound}"):
        logging.info(f"Sound file {environ['DF_DIR']}music/common/{sound} not found.")
        return

    global SOUND_DELAY
    global SOUND_TIMER

    # If the sound is already playing, wait for SOUND_DELAY seconds
    # unless it's a worldrecord sound, then play it immediatly
    if time.time() >= SOUND_TIMER + SOUND_DELAY or sound == 'worldrecord.wav':
        exec_command(f"play music/common/{sound}")
        SOUND_TIMER = time.time()
        return

    logging.info(f"Sound is already playing, cancelling current request !")


def press_key(key, verbose=True):
    try:
        if verbose:
            logging.info(f"Pressing key {key}")
        WINDOW.send(key, blocking=True, press_duration=30)
    except AttributeError:
        logging.info(f"Window not active. {key} was not sent to the client.")


def display_message(message, time=3, y_pos=140, size=10):
    exec_command(f"cg_centertime {time};displaymessage {y_pos} {size} {message}")


# duration in seconds
def hold_key(x, duration):
    try:
        logging.info(f"Holding {x} for {duration} seconds")

        WINDOW.send(x, blocking=True, press_duration=duration * 1000)
    except AttributeError:
        logging.info(f"Window not active. {x} was not sent to the client.")


def reset_visuals():
    exec_command(f"df_chs1_Info6 0;r_picmip 0;r_gamma 1;r_mapoverbrightbits 2;df_mp_NoDrawRadius 100;cg_drawgun 1")
