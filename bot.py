import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import tempfile
from flask import Flask
import threading

# ---------- Keep-alive ----------
app = Flask(__name__)
@app.route('/')
def ping():
    return "I'm alive", 200
def run():
    app.run(host='0.0.0.0', port=8080)
threading.Thread(target=run, daemon=True).start()

# ---------- Bot ----------
bot = commands.Bot(command_prefix='m!', intents=discord.Intents.all())

# ---------- Load cookies ----------
COOKIES_CONTENT = os.getenv('COOKIES_CONTENT')
cookies_file = None
if COOKIES_CONTENT:
    cookies_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
    cookies_file.write(COOKIES_CONTENT)
    cookies_file.flush()
    cookies_file.close()
    print("✅ Cookies loaded.")
else:
    print("⚠️ No cookies – may be blocked.")

# ---------- YDL options ----------
YDL_OPTIONS = {
    'format': 'bestaudio',
    'quiet': False,             # set to True later, but False for debugging
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'extract_flat': False,
}
if cookies_file:
    YDL_OPTIONS['cookiefile'] = cookies_file.name

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

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
            if 'url' not in info:
                raise Exception("No direct URL found")
            url = info['url']
    except Exception as e:
        await voice_client.channel.send(f"❌ Error: {str(e)[:200]}")
        await play_next(guild_id)
        return
    source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
    voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop))
    await voice_client.channel.send(f"🎵 Now playing: **{track.title}**")

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

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

    try:
        if query.startswith(('http://', 'https://')):
            url = query
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
        else:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if not info or 'entries' not in info or not info['entries']:
                    raise Exception("No results found")
                entry = info['entries'][0]
                title = entry['title']
                url = entry['webpage_url']
    except Exception as e:
        await ctx.send(f"❌ Search error: {str(e)[:200]}")
        return

    track = Track(title, url, ctx.author)
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []
    queues[ctx.guild.id].append(track)

    if not voice_client.is_playing():
        await play_next(ctx.guild.id)
    else:
        await ctx.send(f"➕ Added to queue: **{title}**")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ Skipped")
    else:
        await ctx.send("Nothing playing")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id] = []
        await ctx.send("⏹ Stopped and cleared")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queues[ctx.guild.id] = []
        await ctx.send("👋 Left")

# ---------- Token ----------
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("ERROR: DISCORD_TOKEN not set")
    exit(1)
bot.run(TOKEN)
