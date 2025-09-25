
import os, re
from datetime import date
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory

NASA_API_KEY = os.getenv("NASA_API_KEY", "70VHMvXgpuhM9Asn1pGEVdQtGQE0xZY8I2aTv1Z9")
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

def session_with_retries():
    s = requests.Session()
    s.headers.update({"User-Agent": "Rishi-APOD-Web/1.0"})
    retries = Retry(total=3, connect=3, read=3, backoff_factor=0.5,
                    status_forcelist=[429,500,502,503,504], allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

def safe_name(s: str) -> str:
    return re.sub(r'[^-\w\s\(\)\._]', '', s).strip().replace(' ', '_') or "apod"

app = Flask(__name__)

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/apod")
def api_apod():
    d = request.args.get("date")
    params = {"api_key": NASA_API_KEY, "thumbs": True}
    if d:
        params["date"] = d

    s = session_with_retries()
    try:
        r = s.get("https://api.nasa.gov/planetary/apod", params=params, timeout=20)
        # Prefer JSON; fall back to text if NASA returns HTML/error
        try:
            data = r.json()
            return jsonify(data), r.status_code
        except ValueError:
            # Not JSON; return plain text so the browser shows something
            return (r.text, r.status_code, {"Content-Type": "text/plain; charset=utf-8"})
    except requests.RequestException as e:
        app.logger.exception("APOD request failed")
        return jsonify({"error": "APOD request failed", "detail": str(e)}), 502


@app.post("/api/download")
def api_download():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url")
    title = data.get("title") or "apod"
    date_str = data.get("date") or date.today().isoformat()
    if not url:
        return jsonify({"error": "url is required"}), 400

    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    ext = ".jpg"
    for e in (".png",".gif",".jpeg",".jpg",".webp"):
        if path.endswith(e): ext = e; break

    fname = f"APOD_{date_str}_{safe_name(title)}{ext}"
    dest = DOWNLOADS_DIR / fname

    s = session_with_retries()
    try:
        with s.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk: f.write(chunk)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"saved": True, "filename": fname, "path": str(dest.resolve())})

@app.get("/downloads/<path:fname>")
def serve_download(fname):
    return send_from_directory(DOWNLOADS_DIR, fname, as_attachment=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
