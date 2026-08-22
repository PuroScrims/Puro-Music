import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import tempfile
from flask import Flask
import threading
import time
import re

# ---------- Keep-alive web server ----------
app = Flask(__name__)
@app.route('/')
def ping():
    return "I'm alive", 200

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

flask_thread = threading.Thread(target=run_flask, daemon=False)
flask_thread.start()
time.sleep(2)

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

# ---------- YDL options (debug on, permissive format) ----------
YDL_OPTIONS = {
    'format': 'bestaudio/best',           # pick the best audio, any container
    'quiet': False,                       # show yt-dlp output for debugging
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'extract_flat': False,
    'playlistend': 1,
    'extractor_args': {
        'youtube': {
            'player_client': ['web'],     # works with cookies
            'skip': ['dash', 'webpage'],
        }
    },
    # Remove any compat options that might interfere
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

def get_voice_client(guild_id):
    for vc in bot.voice_clients:
        if vc.guild.id == guild_id:
            return vc
    return None

async def play_next(guild_id):
    if guild_id not in queues or not queues[guild_id]:
        return
    track = queues[guild_id].pop(0)
    voice_client = get_voice_client(guild_id)
    if not voice_client:
        return
    try:
        def extract():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(track.url, download=False)
                return info
        info = await asyncio.to_thread(extract)
        if 'url' in info:
            url = info['url']
        elif 'formats' in info and len(info['formats']) > 0:
            best = max(info['formats'], key=lambda f: f.get('abr', 0) or 0)
            url = best['url']
        else:
            raise Exception("No playable URL found")
    except Exception as e:
        await voice_client.channel.send(f"❌ Playback error: {str(e)[:300]}")
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

    # Strip `&list=` from YouTube links
    if 'youtube.com/watch' in query and 'list=' in query:
        video_id = re.search(r'v=([^&]+)', query)
        if video_id:
            query = f"https://www.youtube.com/watch?v={video_id.group(1)}"

    try:
        def search():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                if query.startswith(('http://', 'https://')):
                    info = ydl.extract_info(query, download=False)
                    if 'entries' in info:
                        info = info['entries'][0]
                    return info.get('title', 'Unknown'), query
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if not info or 'entries' not in info or not info['entries']:
                        raise Exception("No results found")
                    entry = info['entries'][0]
                    return entry['title'], entry['webpage_url']
        title, url = await asyncio.to_thread(search)
    except Exception as e:
        await ctx.send(f"❌ Search error: {str(e)[:300]}")
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
