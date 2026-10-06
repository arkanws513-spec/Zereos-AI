import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

PORT = int(os.environ.get("PORT", "8080"))
ROOT = os.path.dirname(os.path.abspath(__file__))

PROVIDERS = [
    ("deepseek", "DEEPSEEK_API_KEY"),
    ("gemini", "GEMINI_API_KEY"),
    ("gemini2", "GEMINI_API_KEY2"),
    ("openai", "OPENAI_API_KEY"),
]

def configured():
    return [name for name, key in PROVIDERS if os.environ.get(key)]

def post_json(url, payload, headers=None, timeout=8):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Provider HTTP {e.code}: {body[:500]}")
    except URLError as e:
        raise RuntimeError(f"Provider connection error: {e.reason}")

def openai_compatible(provider, key, messages, model=None):
    if provider == "openai":
        base, default = "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"
    else:
        base, default = "https://api.deepseek.com/chat/completions", "deepseek-chat"
    payload = {"model": model or default, "messages": messages, "temperature": 0.7}
    data = post_json(base, payload, {"Authorization": f"Bearer {key}"})
    return data["choices"][0]["message"]["content"]

def gemini(key, messages, model=None):
    model = model or "gemini-3.8-flash"
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": str(m["content"])}]})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    data = post_json(url, {"contents": contents})
    return data["candidates"][0]["content"]["parts"][0]["text"]

def ask(message, history, requested_provider=None, requested_model=None):
    messages = [{"role": "system", "content": "You are Zereos, a helpful personal AI assistant. Reply clearly and naturally. Prefer Arabic when the user writes Arabic."}]
    for item in history[-12:]:
        if item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])[:12000]})
    messages.append({"role": "user", "content": message})

    available = configured()
    if requested_provider and requested_provider in available:
        order = [requested_provider] + [x for x in available if x != requested_provider]
    else:
        order = available

    for provider in order:
        key_name = dict(PROVIDERS).get(provider)
        key = os.environ.get(key_name) if key_name else None
        if not key:
            continue
        try:
            if provider.startswith("gemini"):
                return gemini(key, messages, requested_model), provider
            return openai_compatible(provider, key, messages, requested_model), provider
        except Exception:
            continue

    if not available:
        raise RuntimeError("لم يتم إعداد أي مزود ذكاء اصطناعي على الخادم.")
    raise RuntimeError("تعذر الحصول على رد الآن. تمت تجربة مزودي الذكاء الاصطناعي المتاحين.")

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        request_path = urlsplit(self.path).path
        if request_path == "/api/health":
            self.send_json(200, {"ok": True, "providers": configured()})
            return
        path = "/index.html" if request_path in ("/", "") else request_path
        if path.startswith("/"):
            path = path[1:]
        if path != "index.html":
            self.send_response(404)
            self.end_headers()
            return
        try:
            with open(os.path.join(ROOT, "index.html"), "rb") as f:
                raw = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except OSError:
            self.send_response(500)
            self.end_headers()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/chat":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            message = str(body.get("message", "")).strip()
            if not message:
                self.send_json(400, {"error": "Message is required"})
                return
            reply, provider = ask(message, body.get("history", []), body.get("provider"), body.get("model"))
            self.send_json(200, {"reply": reply, "provider": provider})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

if __name__ == "__main__":
    print(f"Zereos listening on 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
