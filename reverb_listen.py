"""
Read-only Reverb/Pusher listener - DEBUG TOOL, not part of the bot.

Connects to the same Reverb server as the bot (creds from src/env.py),
subscribes to the 'defraglive' channel and prints EVERY raw frame that
arrives - including event names. Unlike pysher, nothing is filtered, so
we also see events broadcast under a different name than 'stream'.

Usage:  python reverb_listen.py       (Ctrl+C to exit)
Then click "connect" in the Twitch extension and watch the output.
"""
import json
import os
import ssl
import sys
import time
from datetime import datetime

import websocket  # websocket-client, already installed as a pysher dependency

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
from env import environ

APP_KEY = environ['REVERB_APP_KEY']
HOST = environ['REVERB_HOST']
PORT = environ['REVERB_PORT']
SECURE = str(environ['REVERB_SCHEME']).lower() in ('https', 'wss')

SCHEME = 'wss' if SECURE else 'ws'
URL = f"{SCHEME}://{HOST}:{PORT}/app/{APP_KEY}?protocol=7&client=debug-listener&version=1.0"

CHANNEL = 'defraglive'


def ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]


def on_open(ws):
    print(f"[{ts()}] >>> websocket OPEN: {URL}")


def on_message(ws, raw):
    print(f"[{ts()}] RAW <<< {raw}")

    try:
        frame = json.loads(raw)
    except Exception:
        return

    event = frame.get('event', '')

    if event == 'pusher:connection_established':
        print(f"[{ts()}] >>> connection established, subscribing to '{CHANNEL}'...")
        ws.send(json.dumps({'event': 'pusher:subscribe',
                            'data': {'channel': CHANNEL}}))

    elif event == 'pusher_internal:subscription_succeeded':
        print(f"[{ts()}] >>> SUBSCRIBED to '{frame.get('channel')}' - waiting for events.")
        print(f"[{ts()}] >>> Now click 'connect' in the Twitch extension.")

    elif event == 'pusher:ping':
        ws.send(json.dumps({'event': 'pusher:pong', 'data': {}}))
        print(f"[{ts()}] >>> (answered ping with pong)")

    elif event not in ('pusher:pong',):
        # A real broadcast - unpack it for readability
        print(f"[{ts()}] ================ EVENT ================")
        print(f"[{ts()}]   channel : {frame.get('channel')}")
        print(f"[{ts()}]   event   : {event}")
        data = frame.get('data')
        try:
            payload = json.loads(data) if isinstance(data, str) else data
            print(f"[{ts()}]   payload : {json.dumps(payload, indent=2, ensure_ascii=False)}")
        except Exception:
            print(f"[{ts()}]   payload (raw): {data}")
        print(f"[{ts()}] =======================================")


def on_error(ws, err):
    print(f"[{ts()}] !!! ERROR: {err!r}")


def on_close(ws, code, reason):
    print(f"[{ts()}] !!! CLOSED: code={code} reason={reason!r}")


def main():
    print(f"[{ts()}] Reverb debug listener")
    print(f"[{ts()}]   url     : {URL}")
    print(f"[{ts()}]   channel : {CHANNEL}")
    while True:
        ws = websocket.WebSocketApp(
            URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws.run_forever(sslopt={'cert_reqs': ssl.CERT_NONE} if SECURE else None)
        print(f"[{ts()}] reconnecting in 3s... (Ctrl+C to exit)")
        time.sleep(3)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
