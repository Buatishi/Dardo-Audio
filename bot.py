import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from flask import Flask
import threading

# ------------------------------
# CONFIGURACIÓN
# ------------------------------
TOKEN = "MTQwNjAzMDk5NDM4OTA3ODA5Ng.GYEJKM.4IBxm4141uuyNUQsP4L2W-5EimL4thvP9CAH4M"  # <-- COMPLETAR
PREFIX = "!"
ARCHIVO_DATOS = "tiempos.json"

# ------------------------------
# FUNCIONES DE DATOS
# ------------------------------
def cargar_datos():
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "r") as f:
            return json.load(f)
    return {}

def guardar_datos():
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(tiempos, f)

tiempos = cargar_datos()

def formatear_tiempo(segundos):
    dias, segundos = divmod(segundos, 86400)
    horas, segundos = divmod(segundos, 3600)
    minutos, segundos = divmod(segundos, 60)
    return f"{dias}d, {horas:02}h, {minutos:02}m, {segundos:02}s"

# ------------------------------
# BOT DE DISCORD
# ------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    contar_tiempo.start()

@tasks.loop(seconds=60)
async def contar_tiempo():
    for guild in bot.guilds:
        for member in guild.members:
            if not member.bot:
                tiempos[str(member.id)] = tiempos.get(str(member.id), 0) + 60
    guardar_datos()

@bot.command()
async def ranking(ctx):
    ranking_lista = sorted(tiempos.items(), key=lambda x: x[1], reverse=True)
    mensaje = "**🏆 Ranking de tiempo activo:**\n"
    for i, (user_id, segundos) in enumerate(ranking_lista, start=1):
        usuario = ctx.guild.get_member(int(user_id))
        nombre = usuario.display_name if usuario else "Usuario desconocido"
        mensaje += f"{i}. {nombre} — {formatear_tiempo(segundos)}\n"
    await ctx.send(mensaje)

@bot.command()
async def tiempo(ctx, miembro: discord.Member = None):
    miembro = miembro or ctx.author
    segundos = tiempos.get(str(miembro.id), 0)
    await ctx.send(f"⏳ {miembro.display_name} lleva {formatear_tiempo(segundos)}.")

# ------------------------------
# SERVIDOR WEB PARA UPTIMEROBOT
# ------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot de Discord en funcionamiento"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def mantener_web():
    t = threading.Thread(target=run_web)
    t.start()

# ------------------------------
# INICIO
# ------------------------------
if __name__ == "__main__":
    mantener_web()
    bot.run(TOKEN)
