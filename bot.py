import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from flask import Flask
import threading
from datetime import datetime

# ------------------------------
# CONFIGURACIÓN
# ------------------------------
TOKEN = os.getenv('DISCORD_TOKEN')  # Variable de entorno
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
        json.dump(tiempos, f, indent=4)

# Estructura: {user_id: {"tiempo": segundos, "ultima_vez": timestamp, "en_voz": False}}
tiempos = cargar_datos()

def formatear_tiempo(segundos):
    dias, segundos = divmod(segundos, 86400)
    horas, segundos = divmod(segundos, 3600)
    minutos, segundos = divmod(segundos, 60)
    return f"{dias:02}d, {horas:02}h, {minutos:02}m, {segundos:02}s"

# ------------------------------
# BOT DE DISCORD
# ------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True  # ¡IMPORTANTE PARA VOZ!
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    # Inicializar usuarios ya conectados a voz
    for guild in bot.guilds:
        for member in guild.members:
            if member.voice and not member.bot:
                if str(member.id) not in tiempos:
                    tiempos[str(member.id)] = {"tiempo": 0, "ultima_vez": None, "en_voz": False}
                tiempos[str(member.id)]["en_voz"] = True
                tiempos[str(member.id)]["ultima_vez"] = datetime.now().timestamp()
    
    contar_tiempo.start()
    guardar_datos()

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    user_id = str(member.id)
    
    # Inicializar usuario si no existe
    if user_id not in tiempos:
        tiempos[user_id] = {"tiempo": 0, "ultima_vez": None, "en_voz": False}
    
    # Usuario se conecta a un canal de voz
    if before.channel is None and after.channel is not None:
        tiempos[user_id]["en_voz"] = True
        tiempos[user_id]["ultima_vez"] = datetime.now().timestamp()
        print(f"🔊 {member.display_name} se conectó a {after.channel.name}")
    
    # Usuario se desconecta de un canal de voz
    elif before.channel is not None and after.channel is None:
        if tiempos[user_id]["en_voz"]:
            tiempos[user_id]["en_voz"] = False
            print(f"🔇 {member.display_name} se desconectó de {before.channel.name}")
    
    # Usuario cambia de canal (sigue conectado)
    elif before.channel != after.channel and after.channel is not None:
        tiempos[user_id]["ultima_vez"] = datetime.now().timestamp()
        print(f"🔄 {member.display_name} se movió a {after.channel.name}")
    
    guardar_datos()

@tasks.loop(seconds=30)  # Cada 30 segundos
async def contar_tiempo():
    ahora = datetime.now().timestamp()
    
    for user_id, datos in tiempos.items():
        if datos.get("en_voz", False):
            datos["tiempo"] += 30
            datos["ultima_vez"] = ahora
    
    guardar_datos()

@bot.command(name="ranking")
async def ranking(ctx):
    if not tiempos:
        await ctx.send("📊 No hay datos de tiempo registrados aún.")
        return
    
    # Filtrar solo usuarios con tiempo > 0
    usuarios_con_tiempo = {k: v for k, v in tiempos.items() if v.get("tiempo", 0) > 0}
    
    if not usuarios_con_tiempo:
        await ctx.send("📊 No hay usuarios con tiempo en voz registrado.")
        return
    
    ranking_lista = sorted(usuarios_con_tiempo.items(), key=lambda x: x[1]["tiempo"], reverse=True)
    
    mensaje = "**🏆 Ranking de tiempo en voz:**\n\n"
    
    for i, (user_id, datos) in enumerate(ranking_lista[:10], start=1):  # Top 10
        usuario = ctx.guild.get_member(int(user_id))
        nombre = usuario.display_name if usuario else "Usuario desconocido"
        tiempo_formateado = formatear_tiempo(datos["tiempo"])
        
        # Determinar si está actualmente en voz
        estado = "🔊 En línea" if datos.get("en_voz", False) else "⚫ Offline"
        
        mensaje += f"{i}. **{nombre}** — {tiempo_formateado} {estado}\n"
    
    await ctx.send(mensaje)

@bot.command(name="tiempo")
async def tiempo(ctx, miembro: discord.Member = None):
    miembro = miembro or ctx.author
    user_id = str(miembro.id)
    
    if user_id not in tiempos:
        await ctx.send(f"⏳ {miembro.display_name} no tiene tiempo registrado en voz.")
        return
    
    datos = tiempos[user_id]
    tiempo_formateado = formatear_tiempo(datos["tiempo"])
    
    # Información de última vez
    ultima_vez = datos.get("ultima_vez")
    if ultima_vez:
        fecha = datetime.fromtimestamp(ultima_vez).strftime("%d/%m/%Y %H:%M")
        estado = "🔊 Actualmente en voz" if datos.get("en_voz", False) else f"🕐 Última vez: {fecha}"
    else:
        estado = "❌ Nunca en voz"
    
    await ctx.send(f"⏳ **{miembro.display_name}**\nTiempo total: {tiempo_formateado}\n{estado}")

@bot.command(name="reset")
@commands.has_permissions(administrator=True)
async def reset_datos(ctx, miembro: discord.Member = None):
    if miembro:
        user_id = str(miembro.id)
        if user_id in tiempos:
            tiempos[user_id] = {"tiempo": 0, "ultima_vez": None, "en_voz": False}
            await ctx.send(f"✅ Datos de {miembro.display_name} reiniciados.")
        else:
            await ctx.send(f"❌ {miembro.display_name} no tiene datos registrados.")
    else:
        tiempos.clear()
        await ctx.send("✅ Todos los datos han sido reiniciados.")
    
    guardar_datos()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permisos para usar este comando.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignorar comandos no encontrados
    else:
        print(f"Error: {error}")
        await ctx.send("❌ Ha ocurrido un error al ejecutar el comando.")

# ------------------------------
# SERVIDOR WEB PARA UPTIMEROBOT
# ------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    total_usuarios = len(tiempos)
    usuarios_en_voz = sum(1 for datos in tiempos.values() if datos.get("en_voz", False))
    return f"🤖 Bot Discord activo | Usuarios: {total_usuarios} | En voz: {usuarios_en_voz}"

@app.route("/stats")
def stats():
    return {
        "total_usuarios": len(tiempos),
        "usuarios_en_voz": sum(1 for datos in tiempos.values() if datos.get("en_voz", False)),
        "tiempo_total": sum(datos.get("tiempo", 0) for datos in tiempos.values())
    }

def run_web():
    app.run(host="0.0.0.0", port=8080)

def mantener_web():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

# ------------------------------
# INICIO
# ------------------------------
if __name__ == "__main__":
    mantener_web()
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")