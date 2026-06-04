"""
Web-native transport for DefragLive - replaces the WebSocket link to the
Python bridge. The web (defrag.racing) is now the hub.

Outbound: drains console.WS_Q and POSTs each item to the web API:
  - 'sync_settings' -> /api/defraglive/sync-settings
  - everything else (message / command / serverstate / afk / record / ...)
    -> /api/defraglive/ingest   (web stores it + broadcasts on the channel)

Inbound: subscribes to the public 'defraglive' Reverb channel (Pusher
protocol) and feeds each 'stream' event straight into
websocket_console.on_ws_message - so the bot's existing command handling
(execute_command, ext_command/spectate, viewer chat) runs UNCHANGED. The bot
ignores its own echoed messages because on_ws_message only acts on
execute_command and origin=='twitch' events.

Drop-in for the old websocket_console.ws_worker (same (q, loop) signature);
bot.py just points its ws_thread here instead.
"""
import json
import logging
import time

import requests
import pysher

import config
import console
from websocket_console import on_ws_message, sync_current_settings_to_vps

# Keep a reference to the Pusher client so its connection thread isn't GC'd.
_pusher = None


def _headers():
    return {'Authorization': f'Bearer {config.WEB_INGEST_TOKEN}'}


def _post(path, payload):
    try:
        requests.post(
            config.WEB_BASE_URL + path,
            json=payload,
            headers=_headers(),
            timeout=5,
        )
    except Exception as e:
        logging.error(f"[web] POST {path} failed: {e}")


def _publish_loop(q):
    """Drain WS_Q and forward each item to the web. Blocks on the queue."""
    while True:
        try:
            raw = q.get()  # blocking
            if raw is None or raw == '>>quit<<':
                continue

            try:
                obj = json.loads(raw)
            except Exception:
                logging.error("[web] dropping non-JSON WS_Q item")
                continue

            if obj.get('action') == 'sync_settings':
                _post('/api/defraglive/sync-settings', {'settings': obj.get('settings', {})})
            else:
                _post('/api/defraglive/ingest', obj)
        except Exception as e:
            logging.error(f"[web] publish loop error: {e}")
            time.sleep(0.5)


def _on_stream(data):
    """A live event from the web. `data` is the JSON payload string
    ({action, ...}) - exactly what on_ws_message expects off the old WS."""
    try:
        on_ws_message(data if isinstance(data, str) else json.dumps(data))
    except Exception as e:
        logging.error(f"[web] on_stream error: {e}")


def _start_subscriber():
    pusher = pysher.Pusher(
        key=config.REVERB_APP_KEY,
        custom_host=config.REVERB_HOST,
        port=config.REVERB_PORT,
        secure=(str(config.REVERB_SCHEME).lower() in ('https', 'wss')),
        daemon=True,
    )

    def _connected(_data):
        channel = pusher.subscribe('defraglive')
        channel.bind('stream', _on_stream)
        logging.info("[web] subscribed to 'defraglive' Reverb channel")

    pusher.connection.bind('pusher:connection_established', _connected)
    pusher.connect()
    return pusher


def ws_worker(q, loop=None):
    """Thread entry (same signature bot.py used). `loop` is unused - pysher
    manages its own connection thread."""
    global _pusher

    logging.info("[web] starting web transport (HTTP publish + Reverb subscribe)")

    try:
        _pusher = _start_subscriber()
    except Exception as e:
        logging.error(f"[web] failed to start Reverb subscriber: {e}")

    # Push current game settings to the web once on start (parity with the old
    # on-connect sync); the publisher loop below forwards it.
    try:
        sync_current_settings_to_vps()
    except Exception as e:
        logging.error(f"[web] initial settings sync failed: {e}")

    _publish_loop(q)
