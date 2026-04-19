import subprocess
import os
import shutil
import base64
import requests
import re
from multiprocessing import Pool, cpu_count

# ============================================================
#   LOGS, NORMALIZACIÓN Y DUPLICADOS
# ============================================================

def normalizar_nombre(nombre):
    nombre = nombre.lower()
    nombre = re.sub(r"[^a-z0-9áéíóúñü ]", "", nombre)
    nombre = nombre.replace("  ", " ").strip()
    return nombre

def registrar_descarga_ok(nombre, yt_id):
    with open("descargadas.txt", "a", encoding="utf-8") as f:
        f.write(f"{nombre} | {yt_id}\n")

def registrar_error(nombre, motivo, yt_id="N/A"):
    with open("errores.txt", "a", encoding="utf-8") as f:
        f.write(f"{nombre} | {yt_id} -> {motivo}\n")

def ya_descargada(nombre):
    nombre_norm = normalizar_nombre(nombre)
    if os.path.exists("descargadas.txt"):
        with open("descargadas.txt", "r", encoding="utf-8") as f:
            for linea in f:
                if linea.lower().startswith(nombre_norm):
                    return True
    return False

# ============================================================
#   SPOTIFY
# ============================================================

#============================================================
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""
#============================================================

def spotify_get_token():
    auth = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {"grant_type": "client_credentials"}

    r = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    if r.status_code != 200:
        print("Error obteniendo token de Spotify:", r.text)
        return None

    return r.json()["access_token"]

def spotify_extraer_playlist(url, token):
    try:
        playlist_id = url.split("playlist/")[1].split("?")[0]
    except:
        print("URL de playlist no válida.")
        return None

    headers = {"Authorization": f"Bearer {token}"}

    tracks = []
    next_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"

    while next_url:
        r = requests.get(next_url, headers=headers)
        if r.status_code != 200:
            print("Error obteniendo playlist:", r.text)
            return None

        data = r.json()

        for item in data["items"]:
            track = item["track"]
            if track:
                nombre = track["name"]
                artista = track["artists"][0]["name"]
                tracks.append(f"{nombre} {artista}")

        next_url = data.get("next")

    return tracks

# ============================================================
#   FFMPEG
# ============================================================

def obtener_ruta_ffmpeg():
    ruta_local = os.path.join(os.getcwd(), "ffmpeg", "bin")
    ffmpeg_local = os.path.join(ruta_local, "ffmpeg.exe")
    ffprobe_local = os.path.join(ruta_local, "ffprobe.exe")

    if os.path.exists(ffmpeg_local) and os.path.exists(ffprobe_local):
        return ruta_local

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return None

    return False

# ============================================================
#   SOLO CLIENTE ANDROID
# ============================================================

CLIENTE_ANDROID = ["--extractor-arg", "youtube:player_client=android"]

def extraer_id_youtube(salida):
    match = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", salida)
    if match:
        return match.group(1)
    return "N/A"

# ============================================================
#   DESCARGA (PARA MULTIPROCESSING)
# ============================================================

def descargar_worker(args):
    busqueda, ffmpeg_location = args
    nombre_norm = normalizar_nombre(busqueda)

    if ya_descargada(nombre_norm):
        return

    comando = [
        "yt-dlp",
        f"ytsearch:{busqueda}",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", "%(title)s.%(ext)s",
        "--no-playlist",
        "--remote-components", "ejs:github"
    ] + CLIENTE_ANDROID

    if ffmpeg_location:
        comando += ["--ffmpeg-location", ffmpeg_location]

    resultado = subprocess.run(comando, capture_output=True, text=True)
    salida = resultado.stdout + resultado.stderr
    errores = resultado.stderr.lower()

    yt_id = extraer_id_youtube(salida)

    if resultado.returncode == 0:
        registrar_descarga_ok(nombre_norm, yt_id)
        return

    if "drm" in errores:
        registrar_error(nombre_norm, "DRM detectado", yt_id)
    elif "unavailable" in errores:
        registrar_error(nombre_norm, "Video unavailable", yt_id)
    elif "no video formats" in errores:
        registrar_error(nombre_norm, "Sin formatos disponibles", yt_id)
    else:
        registrar_error(nombre_norm, "Error general", yt_id)

# ============================================================
#   DESCARGA EN PARALELO
# ============================================================

def descargar_en_paralelo(lista):
    ffmpeg_location = obtener_ruta_ffmpeg()

    if ffmpeg_location is False:
        print("No se encontró ffmpeg.")
        return

    args = [(c, ffmpeg_location) for c in lista]

    hilos = max(2, cpu_count() - 1)
    print(f"\nDescargando en paralelo con {hilos} procesos...\n")

    with Pool(hilos) as p:
        p.map(descargar_worker, args)

# ============================================================
#   MENÚ PRINCIPAL
# ============================================================

if __name__ == "__main__":
    print("1. Descargar canción individual")
    print("2. Descargar playlist de Spotify")

    modo = input("Selecciona una opción: ")

    if modo == "1":
        busqueda = input("Introduce la canción o artista: ")
        descargar_worker((busqueda, obtener_ruta_ffmpeg()))

    elif modo == "2":
        url = input("Introduce la URL de la playlist de Spotify: ")

        token = spotify_get_token()
        canciones = spotify_extraer_playlist(url, token)

        print(f"\nSe encontraron {len(canciones)} canciones.\n")
        descargar_en_paralelo(canciones)

    else:
        print("Opción no válida.")

