# import youtube_dl # Remove this line
import yt_dlp       # Use yt-dlp instead
import json
import time
from datetime import datetime, timedelta
import os
import logging # Optional: for better error logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuración
OUTPUT_FILE = 'videos_juegos_mesa.json'
EXTRACTION_INTERVAL = 24 * 3600  # Extracción diaria (en segundos)

# Use channel URLs pointing directly to the 'videos' tab for better results
canales_ingles = {
    "The Dice Tower": "https://www.youtube.com/@TheDiceTower/videos",
    "Shut Up & Sit Down": "https://www.youtube.com/@shutupandsitdown/videos"
}

canales_espanol = {
    "Análisis Parálisis": "https://www.youtube.com/@AnalisisParalisis/videos",
    "El Dado Friki": "https://www.youtube.com/@ElDadoFriki/videos"
}

def extraer_info_canal(canal_url, ultimo_id=None):
    ydl_opts = {
        # 'extract_flat': True, # Remove or set to False to get video details
        'quiet': True,
        'ignoreerrors': True, # Skip videos that cause errors instead of stopping
        'playlistend': 50,    # Limit to fetching info for the latest 50 videos per channel (adjust as needed)
                              # This prevents very long initial fetches or excessive memory use
                              # Remove if you truly need *all* videos every time.
        # 'dateafter': (datetime.now() - timedelta(days=30)).strftime('%Y%m%d'), # Alternative: only fetch videos from last 30 days
    }

    # Use yt_dlp instead of youtube_dl
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            logging.info(f"Attempting to extract info from: {canal_url}")
            # Set download=False
            info_dict = ydl.extract_info(canal_url, download=False)
            videos = []

            if not info_dict or 'entries' not in info_dict:
                 logging.warning(f"No entries found for {canal_url}. Info dict: {info_dict}")
                 return []

            # Need channel info from the main dict *before* looping entries
            channel_name_extracted = info_dict.get('channel', 'Unknown Channel')
            uploader_extracted = info_dict.get('uploader', 'Unknown Uploader') # Sometimes 'uploader' is more reliable

            for entry in info_dict.get('entries', []):
                if not entry: # Skip potential None entries if ignoreerrors=True
                    continue

                video_id = entry.get('id')
                if not video_id:
                    logging.warning(f"Entry missing ID in {canal_url}: {entry.get('title')}")
                    continue

                # Stop if we reach the last known video from the previous run
                if ultimo_id and video_id == ultimo_id:
                    logging.info(f"Reached last known video ID ({ultimo_id}) for {canal_url}. Stopping fetch for this channel.")
                    break

                # Extract thumbnail - often a list, get the last one (usually highest quality)
                thumbnail_url = "No Thumbnail"
                thumbnails = entry.get('thumbnails')
                if isinstance(thumbnails, list) and thumbnails:
                    thumbnail_url = thumbnails[-1].get('url', thumbnail_url)
                elif entry.get('thumbnail'): # Fallback if 'thumbnails' isn't a list
                     thumbnail_url = entry.get('thumbnail')


                video_info = {
                    'id': video_id, # Store the ID for the 'ultimo_id' logic
                    'title': entry.get('title', 'Unknown Title'),
                    'url': entry.get('webpage_url', f"https://www.youtube.com/watch?v={video_id}"), # Prefer webpage_url if available
                    'thumbnail': thumbnail_url,
                    'channel_name': entry.get('channel', channel_name_extracted), # Prefer entry-specific channel name if present
                    'channel_url': entry.get('channel_url', info_dict.get('webpage_url', canal_url)), # Use entry channel_url or fallback
                    'upload_date': entry.get('upload_date'), # YYYYMMDD format
                    'duration': entry.get('duration'), # Seconds
                }
                videos.append(video_info)

            # Reverse the list because YouTube usually returns newest first,
            # and we want to append them in chronological order relative to the existing list
            videos.reverse()
            logging.info(f"Extracted {len(videos)} new videos from {canal_url}")
            return videos

        except yt_dlp.utils.DownloadError as e:
            # Handle specific download errors (like private videos, deleted videos, geo-restrictions)
            logging.error(f"yt-dlp DownloadError for {canal_url}: {e}")
            return []
        except Exception as e:
            # Log other unexpected errors
            logging.exception(f"Unexpected error extracting info from {canal_url}: {e}")
            return []

def guardar_videos(data):
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Data successfully saved to {OUTPUT_FILE}")
    except IOError as e:
        logging.error(f"Failed to write to {OUTPUT_FILE}: {e}")

def cargar_videos():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                logging.info(f"Loading existing data from {OUTPUT_FILE}")
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Failed to load or parse {OUTPUT_FILE}: {e}. Starting fresh.")
            # Optional: backup the corrupted file
            # os.rename(OUTPUT_FILE, OUTPUT_FILE + ".bak")
            return {'ingles': {}, 'espanol': {}}
    logging.info(f"{OUTPUT_FILE} not found. Starting fresh.")
    return {'ingles': {}, 'espanol': {}}

def obtener_info_todos_canales(canales, data_anterior_lang):
    data_actualizada = {}
    for nombre_canal, url_canal in canales.items():
        logging.info(f"Processing channel: {nombre_canal}")

        # Get the list of previously fetched videos for this specific channel
        videos_anteriores = data_anterior_lang.get(nombre_canal, [])

        # Find the ID of the *newest* video we stored last time
        # Assumes videos_anteriores is sorted newest first if loaded from file,
        # OR relies on the reversed list from extraction being appended correctly.
        # Let's assume the stored list is newest first for simplicity here.
        ultimo_video_guardado = videos_anteriores[0] if videos_anteriores else None
        ultimo_id = ultimo_video_guardado.get('id') if ultimo_video_guardado else None

        # logging.info(f"Last known video ID for {nombre_canal}: {ultimo_id}") # Debugging line

        # Extract new videos, stopping if we hit the last known ID
        nuevos_videos = extraer_info_canal(url_canal, ultimo_id)

        # Combine: new videos (now oldest first due to reverse) + old videos
        # Ensure no duplicates if the 'ultimo_id' logic somehow fails slightly
        # A more robust way is to use IDs sets, but this is usually sufficient:
        combined_videos = nuevos_videos + videos_anteriores
        data_actualizada[nombre_canal] = combined_videos

        # Optional: Limit the total number of videos stored per channel
        # MAX_VIDEOS_PER_CHANNEL = 200
        # data_actualizada[nombre_canal] = data_actualizada[nombre_canal][:MAX_VIDEOS_PER_CHANNEL]

        time.sleep(2) # Keep the delay to be polite to YouTube servers

    return data_actualizada

def main():
    while True:
        logging.info("Starting extraction cycle...")
        data_anterior = cargar_videos()

        # Pass only the relevant language part of the data
        info_ingles = obtener_info_todos_canales(canales_ingles, data_anterior.get('ingles', {}))
        info_espanol = obtener_info_todos_canales(canales_espanol, data_anterior.get('espanol', {}))

        data_actual = {'ingles': info_ingles, 'espanol': info_espanol}
        guardar_videos(data_actual)

        logging.info(f"Extraction cycle complete. Waiting for {EXTRACTION_INTERVAL} seconds...")
        time.sleep(EXTRACTION_INTERVAL)

if __name__ == '__main__':
    main()