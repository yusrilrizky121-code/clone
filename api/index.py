import requests
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
    "X-YouTube-Client-Name": "3",
    "X-YouTube-Client-Version": "19.09.37",
}

def get_stream(video_id):
    body = {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.09.37",
                "androidSdkVersion": 30,
                "hl": "en",
                "gl": "US"
            }
        },
        "videoId": video_id,
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
    status = data.get("playabilityStatus", {}).get("status", "UNKNOWN")
    if status != "OK":
        return None, f"playability={status}"

    sd = data.get("streamingData", {})
    formats = sd.get("adaptiveFormats", []) + sd.get("formats", [])
    audio = [f for f in formats
             if f.get("mimeType", "").startswith("audio/")
             and f.get("url")
             and not f.get("signatureCipher")
             and not f.get("cipher")]

    if not audio:
        return None, "no direct audio"

    best = next((f for f in audio if f.get("itag") == 140), None)
    if not best:
        best = max(audio, key=lambda f: f.get("bitrate", 0))
    return best["url"], None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/stream":
            video_id = params.get("videoId", [None])[0]
            if not video_id:
                self._json(400, {"status": "error", "message": "videoId required"})
                return
            try:
                url, err = get_stream(video_id)
                if url:
                    self._json(200, {"status": "success", "url": url})
                else:
                    self._json(200, {"status": "error", "message": err})
            except Exception as e:
                self._json(500, {"status": "error", "message": str(e)})

        elif parsed.path == "/api/search":
            query = params.get("query", [None])[0]
            if not query:
                self._json(400, {"status": "error", "message": "query required"})
                return
            try:
                from ytmusicapi import YTMusic
                results = YTMusic().search(query, filter="songs", limit=12)
                data = [{"videoId": i["videoId"], "title": i.get("title",""), 
                         "artist": i.get("artists",[{}])[0].get("name","") if i.get("artists") else "",
                         "thumbnail": i["thumbnails"][-1]["url"] if i.get("thumbnails") else ""}
                        for i in results if i.get("videoId")]
                self._json(200, {"status": "success", "data": data})
            except Exception as e:
                self._json(500, {"status": "error", "message": str(e)})

        elif parsed.path == "/":
            self._json(200, {"status": "ok", "message": "Auspoty API"})

        else:
            self._json(404, {"status": "error", "message": "not found"})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
