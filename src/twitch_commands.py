import os
from twitchio.ext import commands
import config
import api
import subprocess
import servers
import time
import console
import serverstate
from env import environ
import threading
import asyncio
import websockets
import json
from multiprocessing import Process
import logging
from datetime import datetime
import sys
import pathlib
from mapdata import MapData

USE_WHITELIST = 0

async def connect(ctx, author, args):
    ip = args[0]
    serverstate.connect(ip, author)


async def restart(ctx, author, args):
    serverstate.IGNORE_IPS = []
    connect_ip = servers.get_most_popular_server()
    serverstate.connect(connect_ip)


async def reconnect(ctx, author, args):
    api.exec_command(f"reconnect")


async def reshade(ctx, author, args):
    api.press_key("{F9}")


async def next(ctx, author, args):
    await serverstate.switch_spec('next', channel=ctx.channel)
    api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3{author} ^7has switched to ^3Next player")


async def prev(ctx, author, args):
    await serverstate.switch_spec('prev', channel=ctx.channel)
    api.exec_command(f"cg_centertime 2;displaymessage 140 10 ^3{author} ^7has switched to ^3Previous player")


##async def scores(ctx, author, args):
##    api.hold_key(config.get_bind("+scores"), 4.5)

async def reload(ctx, author, args):
    api.hold_key(config.get_bind("+scores"), 0.0001)


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
        serverstate.PAUSE_STATE = True
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
