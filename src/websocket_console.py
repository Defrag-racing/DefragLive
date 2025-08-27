import asyncio
import websockets
import logging
import time
import json

import api
import console
import config
import serverstate
import filters
import servers

# logger = logging.getLogger('websockets')
# logger.setLevel(logging.DEBUG)
# logger.addHandler(logging.StreamHandler())


def serverstate_to_json():
    data = {
        'bot_id': serverstate.STATE.bot_id,
        'current_player_id': serverstate.STATE.current_player_id,
        # 'idle_counter': serverstate.STATE.idle_counter,
        # 'afk_counter': serverstate.STATE.afk_counter,
        # 'afk_ids': serverstate.STATE.afk_ids,
        'mapname': serverstate.STATE.mapname,
        'df_promode': serverstate.STATE.df_promode,
        'defrag_gametype': serverstate.STATE.defrag_gametype,
        'num_players': serverstate.STATE.num_players,
        'players': {},
    }

    if serverstate.STATE.current_player is not None:
        data['current_player'] = serverstate.STATE.current_player.__dict__

        if 'n' in data['current_player']:
            data['current_player']['n'] = filters.filter_author(data['current_player']['n'])

    for pl in serverstate.STATE.players:
        pl_dict = pl.__dict__

        if 'n' in pl_dict:
            pl_dict['n'] = filters.filter_author(pl_dict['n'])

        data['players'][pl_dict['id']] = pl_dict

    return data

# ------------------------------------------------------------
# - Flask API for the twitch extension
# ------------------------------------------------------------

from flask import Flask, jsonify
app = Flask(__name__)


@app.route('/serverstate.json')
def parsed_serverstate():
    data = serverstate_to_json()
    output = jsonify(data)

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


@app.route('/console.json')
def parsed_console_log():
    output = console.CONSOLE_DISPLAY[-75:] # [::-1] = reversed. console needs new messages at bottom
    output = jsonify(output)

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


@app.route('/console/raw.json')
def raw_console_log():
    output = console.LOG[::-1]
    output = jsonify(output)

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


@app.route('/console/delete_message/<id>')
def delete_message(id):
    output = jsonify({'status': 'ok'})

    for idx, msg in enumerate(console.CONSOLE_DISPLAY):
        if msg['id'] == id:
            del console.CONSOLE_DISPLAY[idx]
            break

    # TODO: fix CORS for production
    output.headers['Access-Control-Allow-Origin'] = '*'

    return output


# ASGI server
def run_flask_server(host, port):
    import uvicorn
    import asgiref.wsgi

    asgi_app = asgiref.wsgi.WsgiToAsgi(app)
    uvicorn.run(asgi_app, host=host, port=port, log_level="warning", access_log=False)


# @app.route('/console/send', methods=['POST'])
# def send_message():
#     author = request.form.get('author', None)
#     message = request.form.get('message', None)
#     command = request.form.get('command', None)

#     if command is not None and command.startswith("!"):
#         if ";" in command:  # prevent q3 command injections
#             command = command[:command.index(";")]
#         api.exec_command(command)
#         return jsonify(result=f"Sent mdd command {command}")
#     else:
#         if ";" in message:  # prevent q3 command injections
#             message = message[:message.index(";")]
#         api.exec_command(f"say {author} ^7> ^2{message}")
#         return jsonify(result=f"Sent {author} ^7> ^2{message}")

#     return jsonify(result="Unknown message")


# ------------------------------------------------------------
# - Websocket client
# ------------------------------------------------------------

def notify_serverstate_change():
    data = serverstate_to_json()

    console.WS_Q.put(json.dumps({'action': 'serverstate', 'message': data}))
    logging.info('--- serverstate change ---')


def handle_ws_command(msg):
    logging.info('[WS] Handle command: %s', str(msg))

    content = msg['message']['content']
    author = 'Guest'
    if 'author' in msg['message']:
        author = msg['message']['author'] if msg['message']['author'] is not None else 'Guest'
    if type(content) is not dict:
        return

    if content['action'] == 'delete_message':
        for idx, msg in enumerate(console.CONSOLE_DISPLAY):
            if msg['id'] == content['id']:
                del console.CONSOLE_DISPLAY[idx]
                break
        return

    if content['action'] == 'spectate':
        logging.info("[CONSOLE] SPECTATE REQUEST")

        if content['value'] == 'next':
            serverstate.switch_spec('next')
            api.exec_command(f"cg_centertime 2;varcommand displaymessage 140 10 ^3{author} ^7has switched to ^3 Next Player")
            time.sleep(1)
            return
        if 'id:' in content['value']:
            id = content['value'].split(':')[1]
            logging.info("[CONSOLE] SPECIFIC ID SPECTATE REQUEST " + str(id))
            serverstate.spectate_player(id)
            api.exec_command(f"cg_centertime 2;varcommand displaymessage 140 10 ^3{author} ^7has switched to ^3 Next Player")
            time.sleep(1)

# NEW: Handle connect action from server browser
    if content['action'] == 'connect':
        ip = content['value']
        logging.info(f"[CONSOLE] CONNECT REQUEST to {ip}")

        # Validate IP (consistent with twitch_commands.py)
        result = servers.is_valid_ip(ip)
        if not result['status']:
            msg = result['message']
            api.exec_command(f"cg_centertime 5;varcommand displaymessage 140 8 ^3{author} ^1{msg};")
            logging.info(msg)
            # Optionally send error back to extension via websocket (e.g., for UI feedback)
            console.WS_Q.put(json.dumps({
                'action': 'connect_error',
                'message': msg
            }))
            return

        # Proceed with connection
        api.exec_command("say ^7Switching servers. ^3Farewell.")
        serverstate.RECONNECTED_CHECK = True
        serverstate.connect(ip, author)
        # Optionally send success back to extension
        console.WS_Q.put(json.dumps({
            'action': 'connect_success',
            'message': f"Connecting to {ip}"
        }))
        return

def on_ws_message(msg):
    message = {}

    if msg is None:
        return

    try:
        message = json.loads(msg)
    except Exception as e:
        logging.info('ERROR [on_ws_message]:', e)
        return

    # if there is no origin, exit
    # this function only processes messages directly from twitch console extension
    if 'origin' not in message:
        return
    if message['origin'] != 'twitch':
        return

    if 'message' in message:
        if message['message'] is None:
            message['message'] = {}

        # Handle actions from twitch extension
        if message['action'] == 'ext_command':
            handle_ws_command(message)
            return

        # Ignore serverstate messages
        if message['action'] == 'serverstate':
            return

        message_text = message['message']['content']

        if ";" in message_text:  # prevent q3 command injections
            message_text = message_text[:message_text.index(";")]

        if message_text.startswith("!"):  # proxy mod commands (!top, !rank, etc.)
            logging.info("proxy command received")
            api.exec_command(message_text)
            time.sleep(1)
        else:
            author = 'Guest'
            if 'author' in message['message']:
                author = message['message']['author']
            author += ' ^7> '
            author_color_num = min(ord(author[0].lower()), 9) # replace ^[a-z] with ^[0-9]
            message_content = message_text.lstrip('>').lstrip('<')
            api.exec_command(f"say ^{author_color_num}{author} ^2{message_content}")


async def ws_send_queue(websocket, q):
    while True:
        if not q.empty():
            msg = q.get()
            # logging.info('ws_send_queue msg: {}'.format(msg))
            if msg == '>>quit<<':
                await websocket.close(reason='KTHXBYE!')
            else:
                await websocket.send(msg)
        else:
            await asyncio.sleep(0)


async def ws_receive(websocket):
    async for msg in websocket:
        # logging.info('ws_receive msg: {}'.format(msg))
        on_ws_message(msg)


# async def start_ws(uri, q):
#     async with websockets.connect(uri) as websocket:
#         while True:
#             async for msg in websocket:
#                 logging.info('ws_receive msg !!!')
#                 on_ws_message(msg)
#                 break

#             if not q.empty():
#                 logging.info('ws_send_queue msg !!!')
#                 msg = q.get()
#                 if msg == '>>quit<<':
#                     await websocket.close(reason='KTHXBYE!')
#                 else:
#                     await websocket.send(msg)

#             await asyncio.sleep(0)


async def ws_start(q):
    async with websockets.connect(config.WS_ADDRESS) as websocket:
        await asyncio.gather(
            ws_receive(websocket),
            ws_send_queue(websocket, q),
        )


def ws_worker(q, loop):
    while True:
        try:
            # loop.run_until_complete(asyncio.wait([
            #     ws_receive(config.WS_ADDRESS),
            #     ws_send_queue(config.WS_ADDRESS, q),
            # ]))
            # loop.create_task(ws_start(q))
            # loop.run_forever()
            loop.run_until_complete(ws_start(q))
        except Exception as e:
            logging.info('\nWebsocket error: {}'.format(str(e)))
            logging.info('Please check if the websocket server is running!\n')
        finally:
            time.sleep(1)
