import config
import api
import servers
import serverstate
import requests
from env import environ
import logging
from mapdata import MapData
from serverstate import send_auto_greeting

USE_WHITELIST = 0


async def connect(ctx, author, args):
    ip = args[0]
    result = servers.is_valid_ip(ip)
    if not result['status']:
        msg = result['message']
        api.exec_command(f"cg_centertime 5;displaymessage 140 8 ^3{author} ^1{msg};")
        logging.info(msg)
        await ctx.channel.send(msg)
        return

    api.exec_command("say ^7Switching servers. ^3Farewell.")

    # Wait 2 seconds before connecting to new server
    time.sleep(2)

    serverstate.RECONNECTED_CHECK = True

    serverstate.connect(ip, author)


async def restart(ctx, author, args):
    serverstate.IGNORE_IPS = []
    connect_ip = servers.get_most_popular_server()
    serverstate.RECONNECTED_CHECK = True
    serverstate.connect(connect_ip)


async def reconnect(ctx, author, args):
    serverstate.RECONNECTED_CHECK = True
    api.exec_command("reconnect")  # This line is already correct in your code


#async def reshade(ctx, author, args):
#    api.press_key("{F9}")


async def next(ctx, author, args):
    await serverstate.switch_spec('next', channel=ctx.channel)
    api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3{author} ^7has switched to ^3Next player")


async def prev(ctx, author, args):
    await serverstate.switch_spec('prev', channel=ctx.channel)
    api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3{author} ^7has switched to ^3Previous player")


##async def scores(ctx, author, args):
##    api.hold_key(config.get_bind("+scores"), 4.5)

##async def reload(ctx, author, args):
##    api.hold_key(config.get_bind("+scores"), 0.0001)


#async def reload(ctx, author, args):
#    key = config.get_bind("+scores")
#    print(f"Key for +scores: {key}")
#    api.hold_key(key, 0.0001)


async def triggers(ctx, author, args):
    api.exec_command(f"toggle r_rendertriggerBrushes 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Render Triggers")


async def clips(ctx, author, args):
    api.exec_command(f"toggle r_renderClipBrushes 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Render Clips")


async def clear(ctx, author, args):
    api.exec_command(f"clear;cg_centertime 3;cg_centertime 3;displaymessage 140 10 ^3{author} ^1Ingame chat has been erased ^3:(")


async def lagometer(ctx, author, args):
    api.exec_command(f"toggle cg_lagometer 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Lagometer")


async def snaps(ctx, author, args):
    api.exec_command(f"toggle mdd_snap 0 3;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3snaps hud")


##async def fixchat(ctx, author, args):
##    api.exec_command(f"cl_noprint 0;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has fixed: ^3ingame chat")


async def cgaz(ctx, author, args):
    api.exec_command(f"toggle mdd_cgaz 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Cgaz hud")


async def nodraw(ctx, author, args):
    api.exec_command(f"toggle df_mp_NoDrawRadius 100 100000;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Players visibility")
    MapData.toggle(serverstate.STATE.mapname, 'nodraw', 100000, 100)


async def angles(ctx, author, args):
    api.exec_command(f"toggle df_chs1_Info6 0 40;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Weapon angles")
    MapData.toggle(serverstate.STATE.mapname, 'angles', 40, 0)


async def obs(ctx, author, args):
    api.exec_command(f"toggle df_chs1_Info7 0 50;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3OverBounces")


async def drawgun(ctx, author, args):
    api.exec_command(f"toggle cg_drawgun 1 2;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Gun movement")
    MapData.toggle(serverstate.STATE.mapname, 'drawgun', 2, 1)


##async def clean(ctx, author, args):
##    api.exec_command(f"toggle cg_draw2D 0 1;wait 10;toggle mdd_hud 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ##^3Clean POV")


async def sky(ctx, author, args):
    api.exec_command(f"toggle r_fastsky 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Sky")


async def speedinfo(ctx, author, args):
    api.exec_command(f"toggle df_chs1_Info5 0 23;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Speedometer (chs info)")


async def speedorig(ctx, author, args):
    api.exec_command(f"toggle df_drawSpeed 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Speedometer (hud element)")


async def gibs(ctx, author, args):
    api.exec_command(f"toggle cg_gibs 1 0;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Gibs after kill")


async def blood(ctx, author, args):
    api.exec_command(f"toggle com_blood 1 0;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Blood after kill")


async def thirdperson(ctx, author, args):
    api.exec_command(f"toggle cg_thirdperson 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Thirdperson POV")


async def miniview(ctx, author, args):
    api.exec_command(f"toggle df_ghosts_MiniviewDraw 0 6;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Miniview")


async def inputs(ctx, author, args):
    api.exec_command(f"toggle df_chs0_draw 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Inputs (WASD...)")


async def slick(ctx, author, args):
    api.exec_command(f"toggle r_renderSlickSurfaces 0 1;cg_centertime 3;displaymessage 140 10 ^3{author} ^7has changed: ^3Slick highlighted")


async def n1(ctx, author, args):
    api.exec_command(f"varcommand say ^{author[0]}{author} ^7> ^2Nice one, $chsinfo(117)^2!")


async def map(ctx, author, args):
    api.exec_command(f"cg_centertime 4;displaymessage 140 10 ^7The current map is: ^3{serverstate.STATE.mapname};")
    msg = f"The current map is: {serverstate.STATE.mapname}"
    await ctx.channel.send(msg)


##async def check(ctx, author, args):
##    api.exec_command(f"r_mapoverbrightbits;r_gamma")


##async def speclist(ctx, author, args):
##    msg = f"Watchable players:" \
##            f" {serverstate.STATE.get_specable_players()} " \
##            f"-- Do ?spec # to spectate a specific player, where # is their id number."
##    await ctx.channel.send(msg)
##    api.hold_key(config.get_bind("+scores"), 4.5)
##
##    if len(serverstate.STATE.nospec_ids) > 0:
##        nospec_msg = f"NOTE: " \
##                f"The following player{'s' if len(serverstate.STATE.nospec_ids) > 1 else ''} " \
##                f"{'have' if len(serverstate.STATE.nospec_ids) > 1 else 'has'} disabled spec permissions: " \
##                f"{serverstate.STATE.get_nospec_players()}"
##        await ctx.channel.send(nospec_msg)


##async def spec(ctx, author, args):
##    follow_id = args[0]
##    msg = serverstate.spectate_player(follow_id)
##    await ctx.channel.send(msg)
##    time.sleep(1)
##    api.exec_command(f"cg_centertime 3;varcommand displaymessage 140 10 ^3{author} ^7has switched to $chsinfo(117)")


async def server(ctx, author, args):
    msg = f"The current server is \"{serverstate.STATE.hostname}\" ({serverstate.STATE.ip})"
    await ctx.channel.send(msg)


async def brightness(ctx, author, args):
    whitelisted_twitch_users = config.get_list('whitelist_twitchusers')
    if USE_WHITELIST and author not in whitelisted_twitch_users and not ctx.author.is_mod:
        await ctx.channel.send(f"{author}, you do not have the correct permissions to use this command. "
                                f"If you wanna be whitelisted to use such a command, please contact neyo#0382 on discord.")
        return
    value = args[0]
    if value.isdigit() and (0 < int(value) <= 5):
        logging.info("vid_restarting...")
        serverstate.VID_RESTARTING = True
        # serverstate.PAUSE_STATE = True
        api.exec_command(f"r_mapoverbrightbits {value};vid_restart")
        MapData.save(serverstate.STATE.mapname, 'brightness', value)
    else:
        await ctx.channel.send(f" {author}, the valid values for brightness are 1-5.")


async def picmip(ctx, author, args):
    whitelisted_twitch_users = config.get_list('whitelist_twitchusers')
    if USE_WHITELIST and author not in whitelisted_twitch_users and not ctx.author.is_mod:
        await ctx.channel.send(f"{author}, you do not have the correct permissions to use this command."
                                f"If you wanna be whitelisted to use such a command, please contact neyo#0382 on discord.")
        return
    value = args[0]
    if value.isdigit() and (0 <= int(value) <= 6):
        logging.info("vid_restarting..")
        serverstate.VID_RESTARTING = True
        serverstate.PAUSE_STATE = True
        api.exec_command(f"r_picmip {value};vid_restart")
        MapData.save(serverstate.STATE.mapname, 'picmip', value)
    else:
        await ctx.channel.send(f"{author}, the allowed values for picmip are 0-5.")


async def fullbright(ctx, author, args):
    whitelisted_twitch_users = config.get_list('whitelist_twitchusers')
    if USE_WHITELIST and author not in whitelisted_twitch_users and not ctx.author.is_mod:
        await ctx.channel.send(f"{author}, you do not have the correct permissions to use this command."
                                f"If you wanna be whitelisted to use such a command, please contact neyo#0382 on discord.")
        return
    value = args[0]
    if value.isdigit() and (0 <= int(value) <= 6):
        logging.info("vid_restarting..")
        serverstate.VID_RESTARTING = True
        serverstate.PAUSE_STATE = True
        api.exec_command(f"r_fullbright {value};vid_restart")
        MapData.save(serverstate.STATE.mapname, 'fullbright', value)
    else:
        await ctx.channel.send(f"{author}, the allowed values for fullbright are 0-1.")


async def gamma(ctx, author, args):
    whitelisted_twitch_users = config.get_list('whitelist_twitchusers')
    if USE_WHITELIST and author not in whitelisted_twitch_users and not ctx.author.is_mod:
        await ctx.channel.send(f"{author}, you do not have the correct permissions to use this command."
                                f"If you wanna be whitelisted to use such a command, please contact neyo#0382 on discord.")
        return
    value = float(args[0])
    if 0.5 <= (value) <= 1.6:
        logging.info("i did it..")
        api.exec_command(f"r_gamma {value}")
        MapData.save(serverstate.STATE.mapname, 'gamma', value)
    else:
        await ctx.channel.send(f"{author}, the allowed values for gamma are 1.0-1.6")


async def ip(ctx, author, args):
    api.exec_command(f"cg_centertime 5;displaymessage 140 8 Current Ip: ^1{serverstate.STATE.ip};")


async def howmany(ctx, author, args):
    client_id = environ['TWITCH_API']['client_id']
    client_secret = environ['TWITCH_API']['client_secret']
    token_url = f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
    r = requests.post(token_url)
    token = r.json()['access_token']
    stream_url = f"https://api.twitch.tv/helix/streams?user_login={'defraglive'}"
    headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
    r = requests.get(stream_url, headers=headers)
    stream_data = r.json()['data']
    viewer_count = stream_data[0]['viewer_count']
    reply_string = f"$chsinfo(117) ^7-- you are being watched by ^3{viewer_count} ^7viewer" + ("s" if viewer_count > 0 else "")
    api.exec_command(f"varcommand say {reply_string}")


async def afk(ctx, author, args):
    """
    Reset or extend AFK counter for the currently spectated player
    Usage: ?afk reset - resets AFK counter to 0
           ?afk extend - extends AFK timeout by 5 minutes (150 strikes)
           ?afk - shows current AFK counter status
    """
    import serverstate
    import api
    import logging
    
    # Check if we have a valid state and are spectating someone
    if not hasattr(serverstate, 'STATE') or serverstate.STATE is None:
        await ctx.channel.send("No active server state available.")
        return
    
    current_player = serverstate.STATE.current_player
    if current_player is None or serverstate.STATE.current_player_id == serverstate.STATE.bot_id:
        await ctx.channel.send("Not currently spectating a player.")
        return
    
    player_name = current_player.n
    current_afk = serverstate.STATE.afk_counter
    
    # Get the current effective AFK timeout for this player
    current_timeout = serverstate.STATE.get_afk_timeout_for_player(serverstate.STATE.current_player_id)
    
    # If no arguments provided, show current status
    if not args:
        remaining = max(0, current_timeout - current_afk)
        time_remaining = remaining * 2  # Each strike is ~2 seconds
        await ctx.channel.send(f"AFK status for {player_name}: {current_afk}/{current_timeout} strikes. "
                             f"~{time_remaining}s until switch.")
        api.exec_command(f"cg_centertime 3;displaymessage 140 10 ^3{author} ^7checked AFK status: ^3{current_afk}^7/^3{current_timeout}")
        return
    
    action = args[0].lower()
    
    if action == "reset":
        # Reset AFK counter to 0
        old_counter = serverstate.STATE.afk_counter
        serverstate.STATE.afk_counter = 0
        
        # Remove from AFK list if they were in it
        if serverstate.STATE.current_player_id in serverstate.STATE.afk_ids:
            serverstate.STATE.afk_ids.remove(serverstate.STATE.current_player_id)
        
        # Clear ignore IPs list
        serverstate.IGNORE_IPS = []
        
        # Reset timeout back to default
        if str(serverstate.STATE.current_player_id) in serverstate.STATE.player_afk_timeouts:
            del serverstate.STATE.player_afk_timeouts[str(serverstate.STATE.current_player_id)]
        
        logging.info(f"AFK counter reset by {author}: {old_counter} -> 0 for player {player_name}")
        await ctx.channel.send(f"AFK counter reset for {player_name} (was {old_counter}/{current_timeout})")
        api.exec_command(f"cg_centertime 3;displaymessage 140 10 ^3{author} ^7reset AFK counter for ^3{player_name}")
        
    elif action == "extend":
        # Extend by 5 minutes (150 strikes, since each strike is ~2 seconds)
        extension_strikes = 150
        old_counter = serverstate.STATE.afk_counter
        old_timeout = current_timeout
        
        # Set a new custom timeout for this player
        new_timeout = current_afk + extension_strikes
        serverstate.STATE.set_afk_timeout_for_player(serverstate.STATE.current_player_id, new_timeout)
        
        strikes_remaining = new_timeout - current_afk
        extended_time = strikes_remaining * 2  # strikes × 2 seconds
        
        logging.info(f"AFK timeout extended by {author}: timeout {old_timeout} -> {new_timeout} for player {player_name} (gave {extension_strikes} additional strikes = ~{extended_time}s)")
        
        # Send to both Twitch chat and in-game
        msg = f"Extended AFK timer for {player_name} by 5 minutes - now at {current_afk}/{new_timeout} (~{extended_time}s until switch)"
        await ctx.channel.send(msg)
        api.exec_command(f"say ^3{author} ^7extended AFK timer for ^3{player_name} ^7by 5 minutes")
        api.exec_command(f"cg_centertime 3;displaymessage 140 10 ^3{author} ^7extended AFK timer for ^3{player_name} ^7by 5 minutes")
        
    else:
        await ctx.channel.send(f"{author}, usage: ?afk [reset|extend] or just ?afk to check status")

async def greeting(ctx, author, args):
    """Test command to trigger greeting manually"""
    send_auto_greeting()
    await ctx.channel.send("Manual greeting sent!")