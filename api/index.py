from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import requests
import time
import json

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

home_cache = {}
CACHE_TTL = 1800

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
    "X-YouTube-Client-Name": "3",
    "X-YouTube-Client-Version": "19.09.37",
}

def innertube_context():
    return {
        "client": {
            "clientName": "ANDROID",
            "clientVersion": "19.09.37",
            "androidSdkVersion": 30,
            "hl": "id",
            "gl": "ID"
        }
    }

def format_results(search_results):
    cleaned = []
    for item in search_results:
        if 'videoId' in item:
            cleaned.append({
                "videoId": item['videoId'],
                "title": item.get('title', 'Unknown'),
                "artist": item.get('artists', [{'name': 'Unknown'}])[0]['name'] if item.get('artists') else 'Unknown',
                "thumbnail": item['thumbnails'][-1]['url'] if item.get('thumbnails') else ''
            })
    return cleaned

@app.get("/api/stream")
def get_stream_url(videoId: str):
    try:
        body = {
            "context": innertube_context(),
            "videoId": videoId,
            "contentCheckOk": True,
            "racyCheckOk": True
        }
        r = requests.post(
            "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
            headers=HEADERS,
            json=body,
            timeout=20
        )
        data = r.json()
        status = data.get("playabilityStatus", {}).get("status")
        if status != "OK":
            return {"status": "error", "message": f"playability: {status}"}

        sd = data.get("streamingData", {})
        formats = sd.get("adaptiveFormats", []) + sd.get("formats", [])

        # Cari audio direct URL (tanpa cipher)
        audio = [f for f in formats
                 if f.get("mimeType", "").startswith("audio/")
                 and f.get("url")
                 and not f.get("signatureCipher")
                 and not f.get("cipher")]

        if not audio:
            return {"status": "error", "message": "no direct audio url"}

        # Pilih itag 140 (m4a 128k) atau bitrate tertinggi
        best = next((f for f in audio if f.get("itag") == 140), None)
        if not best:
            best = max(audio, key=lambda f: f.get("bitrate", 0))

        return {"status": "success", "url": best["url"]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/search")
def search_music(query: str):
    try:
        from ytmusicapi import YTMusic
        ytmusic = YTMusic()
        results = ytmusic.search(query, filter="songs", limit=12)
        return {"status": "success", "data": format_results(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/home")
def get_home_data():
    current_time = time.time()
    if "data" in home_cache and (current_time - home_cache.get("timestamp", 0) < CACHE_TTL):
        return {"status": "success", "data": home_cache["data"]}
    try:
        from ytmusicapi import YTMusic
        ytmusic = YTMusic()
        queries = {
            "recent":  "lagu indonesia hits terbaru",
            "anyar":   "lagu pop indonesia rilis terbaru anyar",
            "gembira": "lagu ceria gembira semangat",
            "charts":  "top 50 indonesia playlist update",
            "galau":   "lagu galau sedih indonesia terpopuler",
            "baru":    "lagu viral terbaru 2026",
            "tiktok":  "lagu fyp tiktok viral jedag jedug",
            "artists": "penyanyi pop indonesia paling hits",
        }
        data = {k: format_results(ytmusic.search(v, filter="songs", limit=8)) for k, v in queries.items()}
        home_cache["data"] = data
        home_cache["timestamp"] = current_time
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/lyrics")
def get_lyrics(video_id: str):
    try:
        from ytmusicapi import YTMusic
        ytmusic = YTMusic()
        watch = ytmusic.get_watch_playlist(video_id)
        lyrics_id = watch.get("lyrics")
        if not lyrics_id:
            return {"status": "error", "message": "No lyrics found"}
        lyrics = ytmusic.get_lyrics(lyrics_id)
        text = lyrics.get("lyrics", "")
        if not text:
            return {"status": "error", "message": "Empty lyrics"}
        return {"status": "success", "data": {"lyrics": text}}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
def root():
    return {"status": "ok", "message": "Auspoty Music API v2"}

handler = Mangum(app)
