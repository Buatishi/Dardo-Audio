import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from flask import Flask
import threading
from datetime import datetime
import shutil
import time

# ------------------------------
# CONFIGURACIÓN
# ------------------------------
TOKEN = os.getenv('DISCORD_TOKEN')  # Variable de entorno
PREFIX = "!"
ARCHIVO_DATOS = "tiempos.json"
BACKUP_DATOS = "tiempos_backup.json"
BACKUP_INTERVAL = 300  # 5 minutos

# ------------------------------
# FUNCIONES DE DATOS CON BACKUP
# ------------------------------
def cargar_datos():
    """Carga datos con sistema de backup automático"""
    datos = {}
    
    try:
        # Intentar cargar archivo principal
        if os.path.exists(ARCHIVO_DATOS):
            with open(ARCHIVO_DATOS, "r", encoding='utf-8') as f:
                datos = json.load(f)
            print(f"✅ Datos cargados desde {ARCHIVO_DATOS}")
            
        # Si no existe, intentar backup
        elif os.path.exists(BACKUP_DATOS):
            with open(BACKUP_DATOS, "r", encoding='utf-8') as f:
                datos = json.load(f)
            print(f"🔄 Datos recuperados desde backup {BACKUP_DATOS}")
            # Restaurar archivo principal
            guardar_datos_archivo(datos, ARCHIVO_DATOS)
            
        else:
            print("📄 No hay datos previos, comenzando desde cero")
            
    except (json.JSONDecodeError, IOError) as e:
        print(f"❌ Error cargando {ARCHIVO_DATOS}: {e}")
        
        # Intentar backup si falla archivo principal
        try:
            if os.path.exists(BACKUP_DATOS):
                with open(BACKUP_DATOS, "r", encoding='utf-8') as f:
                    datos = json.load(f)
                print(f"🆘 Datos recuperados desde backup después del error")
                # Restaurar archivo principal
                guardar_datos_archivo(datos, ARCHIVO_DATOS)
        except Exception as backup_error:
            print(f"❌ Error también en backup: {backup_error}")
            print("🔄 Iniciando con datos vacíos")
            
    return datos

def guardar_datos_archivo(datos, archivo):
    """Guarda datos en un archivo específico de forma segura"""
    try:
        # Escribir a archivo temporal primero
        archivo_temp = f"{archivo}.tmp"
        with open(archivo_temp, "w", encoding='utf-8') as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
        
        # Mover archivo temporal al final (operación atómica)
        shutil.move(archivo_temp, archivo)
        
    except Exception as e:
        print(f"❌ Error guardando {archivo}: {e}")
        # Limpiar archivo temporal si existe
        if os.path.exists(f"{archivo}.tmp"):
            os.remove(f"{archivo}.tmp")

def guardar_datos():
    """Guarda datos con backup automático"""
    guardar_datos_archivo(tiempos, ARCHIVO_DATOS)
    
def crear_backup():
    """Crea backup de los datos cada cierto tiempo"""
    try:
        if os.path.exists(ARCHIVO_DATOS):
            shutil.copy2(ARCHIVO_DATOS, BACKUP_DATOS)
            print(f"💾 Backup creado: {BACKUP_DATOS}")
    except Exception as e:
        print(f"❌ Error creando backup: {e}")

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
    # Crear backup inicial de los datos existentes
    crear_backup()
    
    # Inicializar usuarios ya conectados a voz al iniciar el bot
    for guild in bot.guilds:
        for member in guild.members:
            if member.voice and not member.bot:
                user_id = str(member.id)
                if user_id not in tiempos:
                    tiempos[user_id] = {"tiempo": 0, "ultima_vez": None, "en_voz": False}
                tiempos[user_id]["en_voz"] = True
                tiempos[user_id]["ultima_vez"] = datetime.now().timestamp()
                print(f"🔊 {member.display_name} ya estaba en voz al iniciar")
    
    # Iniciar tareas automáticas
    contar_tiempo.start()
    backup_automatico.start()
    guardar_datos()
    print("🔄 Sistema de backup automático activado cada 5 minutos")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    user_id = str(member.id)
    ahora = datetime.now().timestamp()
    
    # Inicializar usuario si no existe
    if user_id not in tiempos:
        tiempos[user_id] = {"tiempo": 0, "ultima_vez": None, "en_voz": False}
    
    # Usuario se conecta a un canal de voz
    if before.channel is None and after.channel is not None:
        tiempos[user_id]["en_voz"] = True
        tiempos[user_id]["ultima_vez"] = ahora
        print(f"🔊 {member.display_name} se conectó a {after.channel.name}")
    
    # Usuario se desconecta de un canal de voz
    elif before.channel is not None and after.channel is None:
        if tiempos[user_id]["en_voz"] and tiempos[user_id]["ultima_vez"]:
            # Calcular tiempo de la sesión que acaba de terminar
            tiempo_sesion = int(ahora - tiempos[user_id]["ultima_vez"])
            tiempos[user_id]["tiempo"] += tiempo_sesion
            print(f"🔇 {member.display_name} se desconectó después de {tiempo_sesion}s")
        
        tiempos[user_id]["en_voz"] = False
        tiempos[user_id]["ultima_vez"] = ahora
    
    # Usuario cambia de canal (sigue conectado)
    elif before.channel != after.channel and after.channel is not None:
        tiempos[user_id]["ultima_vez"] = ahora
        print(f"🔄 {member.display_name} se movió a {after.channel.name}")
    
    guardar_datos()

@tasks.loop(seconds=10)  # Cada 10 segundos para mayor precisión
async def contar_tiempo():
    ahora = datetime.now().timestamp()
    
    for user_id, datos in tiempos.items():
        if datos.get("en_voz", False) and datos.get("ultima_vez"):
            # Solo actualizar si ha pasado tiempo suficiente
            tiempo_transcurrido = int(ahora - datos["ultima_vez"])
            if tiempo_transcurrido >= 10:
                datos["tiempo"] += tiempo_transcurrido
                datos["ultima_vez"] = ahora
    
    guardar_datos()

# Task para crear backups automáticos
@tasks.loop(seconds=BACKUP_INTERVAL)  # Cada 5 minutos
async def backup_automatico():
    crear_backup()

@bot.command(name="ranking")
async def ranking(ctx):
    if not tiempos:
        await ctx.send("📊 No hay datos de tiempo registrados aún.")
        return
    
    # Filtrar solo usuarios con tiempo >= 1 segundo
    usuarios_con_tiempo = {k: v for k, v in tiempos.items() if v.get("tiempo", 0) >= 1}
    
    if not usuarios_con_tiempo:
        await ctx.send("📊 No hay usuarios con tiempo en voz registrado.")
        return
    
    ranking_lista = sorted(usuarios_con_tiempo.items(), key=lambda x: x[1]["tiempo"], reverse=True)
    
    # Crear mensaje con mejor formato estético
    mensaje = "```\n"
    mensaje += "🏆═══════════════════════════════════════════════════════🏆\n"
    mensaje += "              📊 RANKING DE TIEMPO EN VOZ 📊              \n"
    mensaje += "🏆═══════════════════════════════════════════════════════🏆\n\n"
    
    # Mostrar TODOS los usuarios con al menos 1 segundo
    for i, (user_id, datos) in enumerate(ranking_lista, start=1):
        usuario = ctx.guild.get_member(int(user_id))
        nombre = usuario.display_name if usuario else "Usuario desconocido"
        tiempo_formateado = formatear_tiempo(datos["tiempo"])
        
        # Determinar emoji de posición y estado
        if i == 1:
            emoji_pos = "🥇"
        elif i == 2:
            emoji_pos = "🥈"
        elif i == 3:
            emoji_pos = "🥉"
        else:
            emoji_pos = f"{i:2d}."
        
        estado = "🔊" if datos.get("en_voz", False) else "⚫"
        
        # Ajustar formato para que se vea alineado  
        nombre_fmt = nombre[:20].ljust(20) if len(nombre) <= 20 else nombre[:17] + "..."
        mensaje += f"{emoji_pos} {nombre_fmt} │ {tiempo_formateado} {estado}\n"
    
    mensaje += "\n═══════════════════════════════════════════════════════\n"
    mensaje += f"Total de usuarios registrados: {len(ranking_lista)}\n" 
    mensaje += "```"
    
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