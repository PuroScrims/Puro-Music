import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import tempfile
from flask import Flask
import threading

# ---------- Keep‑alive web server ----------
app = Flask(__name__)
@app.route('/')
def ping():
    return "I'm alive", 200
def run():
    app.run(host='0.0.0.0', port=8080)
threading.Thread(target=run, daemon=True).start()

# ---------- Bot ----------
bot = commands.Bot(command_prefix='m!', intents=discord.Intents.all())

YDL_OPTIONS = {'format': 'bestaudio/best', 'quiet': True}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1', 'options': '-vn'}

queues = {}

class Track:
    def __init__(self, title, url, requester):
        self.title = title
        self.url = url
        self.requester = requester

async def play_next(guild_id):
    if guild_id not in queues or not queues[guild_id]:
        return
    track = queues[guild_id].pop(0)
    voice_client = bot.voice_clients.get(guild_id)
    if not voice_client:
        return
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(track.url, download=False)
            url = info['url']
    except:
        await voice_client.channel.send("Error loading track")
        await play_next(guild_id)
        return
    source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
    voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop))
    await voice_client.channel.send(f"Now playing: **{track.title}**")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command(name='p')
async def play(ctx, *, query=None):
    if not query:
        await ctx.send("Give a song name or link")
        return
    if not ctx.author.voice:
        await ctx.send("Join a voice channel first")
        return
    voice_client = ctx.voice_client
    if not voice_client:
        await ctx.author.voice.channel.connect()
        voice_client = ctx.voice_client
    if query.startswith(('http://', 'https://')):
        url = query
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
    else:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            info = info['entries'][0]
            title = info['title']
            url = info['webpage_url']
    track = Track(title, url, ctx.author)
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []
    queues[ctx.guild.id].append(track)
    if not voice_client.is_playing():
        await play_next(ctx.guild.id)
    else:
        await ctx.send(f"Added to queue: {title}")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipped")
    else:
        await ctx.send("Nothing playing")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id] = []
        await ctx.send("Stopped & cleared")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queues[ctx.guild.id] = []
        await ctx.send("Left")

# ---------- THIS READS THE TOKEN FROM RENDER'S SECRET SETTINGS ----------
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    print("ERROR: DISCORD_TOKEN not set in environment variables!")
    exit(1)

bot.run(TOKEN)
