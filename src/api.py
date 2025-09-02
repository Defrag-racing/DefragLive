import os
import time
from env import environ
import logging

from ahk import AHK

import config


# AHK = AHK()
AHK = AHK(executable_path='C:\\Program Files\\AutoHotkey\\AutoHotkey.exe')
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
    """Grab both engine and console windows with better error handling"""
    global CONSOLE
    global WINDOW

    try:
        # Existing console setup code...
        if environ["DEVELOPMENT"]:
            CONSOLE = AHK.run_script("WinShow," + CONSOLEWINDOW +
                       "\nControlGet, console, Hwnd ,, Edit1, " + CONSOLEWINDOW +
                       "\nFileAppend, %console%, * ;", blocking=True)
        else:
            CONSOLE = AHK.run_script("WinShow," + CONSOLEWINDOW + \
                        "\nControlGet, console, Hwnd ,, Edit1, " + CONSOLEWINDOW +
                        "\nWinHide," + CONSOLEWINDOW +
                        "\nFileAppend, %console%, * ;", blocking=True)
        
        WINDOW = AHK.find_window(title="TwitchBot Engine")
        
        # Better validation
        if CONSOLE is None:
            raise WindowNotFoundError("Console window not found")
        if WINDOW is None:
            raise WindowNotFoundError("Engine window not found") 
        if not WINDOW.exists:
            raise WindowNotFoundError("Engine window exists but is not accessible")
            
    except Exception as e:
        logging.error(f"Window initialization failed: {e}")
        raise WindowNotFoundError(f"Could not initialize windows: {e}")


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
        
        # Add window validation before sending
        if not WINDOW or not WINDOW.exists:
            logging.info(f"Window not found or inactive. {key} was not sent.")
            return
            
        # Verify window is still the game window
        if "TwitchBot Engine" not in WINDOW.title:
            logging.info(f"Window title changed. {key} was not sent to prevent leaking.")
            return
            
        WINDOW.send(key, blocking=True, press_duration=30)
        
    except (AttributeError, Exception) as e:
        logging.info(f"Failed to send key {key}: {e}. Window may not be active.")


def hold_key(x, duration):
    try:
        logging.info(f"Holding {x} for {duration} seconds")
        
        # Add window validation
        if not WINDOW or not WINDOW.exists:
            logging.info(f"Window not found. {x} hold cancelled.")
            return
            
        if "TwitchBot Engine" not in WINDOW.title:
            logging.info(f"Wrong window active. {x} hold cancelled.")
            return
        
        # Send key down to specific window
        WINDOW.send(x, blocking=True)
        time.sleep(duration)
        
        # Use window-specific key release instead of global AHK script
        WINDOW.send(f"{x} up", blocking=True)
        
    except (AttributeError, Exception) as e:
        logging.info(f"Failed to hold key {x}: {e}. Window interaction failed.")
        # Ensure key is released even if there's an error
        try:
            AHK.run_script(f"Send {{{x} up}}", blocking=True)
        except:
            pass  # If this fails too, at least we tried


def reset_visuals():
    exec_command(f"df_chs1_Info6 0;r_picmip 0;r_gamma 1;r_mapoverbrightbits 2;df_mp_NoDrawRadius 100;cg_drawgun 1")
