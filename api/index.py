import requests
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse

CLIENTS = [
    {
        "name": "ANDROID_TESTSUITE",
        "version": "1.9.38.43",
        "id": "30",
        "ua": "com.google.android.youtube/1.9.38.43 (Linux; U; Android 11) gzip",
        "extra": {"osName": "Android", "osVersion": "11", "androidSdkVersion": "30"}
    },
    {
        "name": "ANDROID_VR",
        "version": "1.65.10",
        "id": "28",
        "ua": "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; en_US; Quest 3; Build/SQ3A.220605.009.A1; Cronet/132.0.6808.3)",
        "extra": {"osName": "Android", "osVersion": "12L", "deviceMake": "Oculus", "deviceModel": "Quest 3", "androidSdkVersion": "32"}
    },
    {
        "name": "ANDROID",
        "version": "19.09.37",
        "id": "3",
        "ua": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
        "extra": {"osName": "Android", "osVersion": "11", "androidSdkVersion": "30"}
    },
]

def get_audio_url(video_id):
    for client in CLIENTS:
        try:
            ctx = {"clientName": client["name"], "clientVersion": client["version"], "hl": "en", "gl": "US"}
            ctx.update(client["extra"])
            body = {"context": {"client": ctx}, "videoId": video_id, "contentCheckOk": True, "racyCheckOk": True}
            headers = {
                "Content-Type": "application/json",
                "User-Agent": client["ua"],
                "X-YouTube-Client-Name": client["id"],
                "X-YouTube-Client-Version": client["version"],
            }
            r = requests.post(
                "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
                headers=headers, json=body, timeout=15
            )
            data = r.json()
            if data.get("playabilityStatus", {}).get("status") != "OK":
                continue
            sd = data.get("streamingData", {})
            formats = sd.get("adaptiveFormats", []) + sd.get("formats", [])
            audio = [f for f in formats
                     if f.get("mimeType", "").startswith("audio/")
                     and f.get("url")
                     and not f.get("signatureCipher")
                     and not f.get("cipher")]
            if not audio:
                continue
            # Prefer itag 140 (m4a 128kbps) or highest bitrate
            best = next((f for f in audio if f.get("itag") == 140), None)
            if not best:
                best = max(audio, key=lambda f: f.get("bitrate", 0))
            url = best.get("url")
            if url:
                return url, client["ua"]
        except Exception:
            continue
    return None, None


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
                url, ua = get_audio_url(video_id)
                if not url:
                    self._json(200, {"status": "error", "message": "all clients failed"})
                    return
                # Proxy the audio stream directly to the client
                # This bypasses IP-binding issue — Vercel fetches, client receives
                stream_headers = {
                    "User-Agent": ua,
                    "Referer": "https://www.youtube.com/",
                    "Origin": "https://www.youtube.com",
                }
                range_header = self.headers.get("Range")
                if range_header:
                    stream_headers["Range"] = range_header

                yt_resp = requests.get(url, headers=stream_headers, stream=True, timeout=30)
                
                self.send_response(yt_resp.status_code)
                for h in ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]:
                    val = yt_resp.headers.get(h)
                    if val:
                        self.send_header(h, val)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                
                for chunk in yt_resp.iter_content(chunk_size=65536):
               
                    if chunk:
                        self.wfile.write(chunk)

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
                data = [{"videoId": i["videoId"], "title": i.get("title", ""),
                         "artist": i.get("artists", [{}])[0].get("name", "") if i.get("artists") else "",
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
