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


def github_request(path, method="GET", payload=None):
    """GitHub API request. Writes require a server-side token with repository contents permissions."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Zereos-AI"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request("https://api.github.com" + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {body[:400]}")

def github_write_action(body):
    """Perform an authenticated, explicitly requested GitHub file operation."""
    import hmac
    expected = os.environ.get("ZEREOS_ADMIN_TOKEN", "").strip()
    supplied = str(body.get("admin_token", "")).strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise PermissionError("يلزم إدخال مفتاح إدارة زيريوس الصحيح.")
    if not os.environ.get("GITHUB_TOKEN", "").strip():
        raise RuntimeError("لم يُضبط GITHUB_TOKEN على الخادم. أضف GitHub token بصلاحية Contents: Read and write.")
    action = str(body.get("action", "")).lower().strip()
    repo = str(body.get("repo", "")).strip()
    path = str(body.get("path", "")).strip().lstrip("/")
    message = str(body.get("message", "")).strip()[:200]
    branch = str(body.get("branch", "")).strip()
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("اسم المستودع يجب أن يكون owner/repo.")
    if not path or path.startswith("../") or "/../" in path or path == "..":
        raise ValueError("مسار الملف غير صالح.")
    if not message:
        message = {"create": "Create file via Zereos AI", "update": "Update file via Zereos AI", "delete": "Delete file via Zereos AI"}.get(action, "GitHub change via Zereos AI")
    from urllib.parse import quote
    api_path = f"/repos/{repo}/contents/{quote(path, safe='/')}"
    if branch:
        api_path += "?ref=" + quote(branch, safe="")
    if action in ("create", "update"):
        content = body.get("content")
        if not isinstance(content, str):
            raise ValueError("محتوى الملف يجب أن يكون نصًا.")
        if len(content) > 500000:
            raise ValueError("حجم الملف يتجاوز الحد المسموح (500 KB).")
        payload = {"message": message, "content": __import__("base64").b64encode(content.encode("utf-8")).decode("ascii")}
        if branch:
            payload["branch"] = branch
        if action == "update":
            current = github_request(api_path)
            if not current.get("sha"):
                raise RuntimeError("لم يتم العثور على الملف الحالي.")
            payload["sha"] = current["sha"]
        result = github_request(api_path.split("?")[0], "PUT", payload)
        return {"ok": True, "action": action, "repo": repo, "path": path, "commit": result.get("commit", {}).get("sha"), "url": result.get("content", {}).get("html_url")}
    if action == "delete":
        if str(body.get("confirm", "")).strip() != "DELETE":
            raise ValueError("لحذف ملف، أرسل confirm=DELETE صراحةً.")
        current = github_request(api_path)
        payload = {"message": message, "sha": current["sha"]}
        if branch:
            payload["branch"] = branch
        result = github_request(api_path.split("?")[0], "DELETE", payload)
        return {"ok": True, "action": action, "repo": repo, "path": path, "commit": result.get("commit", {}).get("sha")}
    raise ValueError("العملية المدعومة: create أو update أو delete.")


def github_context_for_message(message):
    """Fetch bounded, read-only repository context when the user explicitly asks about GitHub."""
    import re
    text = str(message)
    match = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text, re.I)
    try:
        if match:
            owner, repo = match.group(1), match.group(2).removesuffix(".git")
            meta = github_request(f"/repos/{owner}/{repo}")
            result = {
                "repository": meta.get("full_name"),
                "description": meta.get("description"),
                "default_branch": meta.get("default_branch"),
                "language": meta.get("language"),
                "private": meta.get("private"),
                "html_url": meta.get("html_url"),
            }
            try:
                readme = github_request(f"/repos/{owner}/{repo}/readme")
                import base64
                result["readme"] = base64.b64decode(readme.get("content", "")).decode("utf-8", errors="replace")[:7000]
            except Exception:
                result["readme"] = "(README unavailable)"
            try:
                contents = github_request(f"/repos/{owner}/{repo}/contents")
                result["root_files"] = [
                    {"name": item.get("name"), "type": item.get("type"), "path": item.get("path")}
                    for item in contents[:60]
                ] if isinstance(contents, list) else []
            except Exception:
                result["root_files"] = []
            file_match = re.search(r"github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/blob/([^/]+)/(.+?)(?:[?#].*)?$", text, re.I)
            if file_match:
                branch, file_path = file_match.group(1), file_match.group(2)
                try:
                    from urllib.parse import quote
                    file_data = github_request(f"/repos/{owner}/{repo}/contents/{quote(file_path, safe='/')}?ref={quote(branch, safe='')}")
                    if file_data.get("encoding") == "base64":
                        import base64
                        result["requested_file"] = {
                            "path": file_path,
                            "content": base64.b64decode(file_data.get("content", "")).decode("utf-8", errors="replace")[:12000]
                        }
                except Exception as exc:
                    result["requested_file_error"] = type(exc).__name__
            return "\n\nGitHub repository context (read-only, retrieved live):\n" + json.dumps(result, ensure_ascii=False)[:18000]
        if re.search(r"github|جيت\s*هاب", text, re.I) and re.search(r"ابحث|بحث|search|مستودع|مستودعات|repository|repositories", text, re.I):
            query = re.sub(r"(?is).*?(?:ابحث(?:\s+لي)?|بحث|search)\s+(?:في\s+)?(?:جيت\s*هاب|github)?\s*(?:عن|for)?\s*", "", text).strip()
            query = query[:180]
            if query:
                from urllib.parse import quote
                data = github_request("/search/repositories?q=" + quote(query) + "&per_page=8")
                items = [{
                    "full_name": x.get("full_name"),
                    "description": x.get("description"),
                    "html_url": x.get("html_url"),
                    "language": x.get("language"),
                    "stars": x.get("stargazers_count"),
                } for x in data.get("items", [])]
                return "\n\nLive GitHub repository search results (read-only):\n" + json.dumps(items, ensure_ascii=False)[:8000]
    except Exception as exc:
        return "\n\nGitHub lookup failed: " + type(exc).__name__ + ". Tell the user to check GITHUB_TOKEN on the server if the repository is private or rate limits are reached."
    return ""

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
        request_path = urlsplit(self.path).path
        if request_path == "/api/github/write":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                result = github_write_action(body)
                self.send_json(200, result)
            except PermissionError as e:
                self.send_json(401, {"error": str(e)})
            except Exception as e:
                self.send_json(400, {"error": str(e)})
            return
        if request_path != "/api/chat":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            message = str(body.get("message", "")).strip()
            if not message:
                self.send_json(400, {"error": "Message is required"})
                return
            github_context = github_context_for_message(message)
            if github_context:
                message = message + "\n\n" + github_context
            reply, provider = ask(message, body.get("history", []), body.get("provider"), body.get("model"))
            self.send_json(200, {"reply": reply, "provider": provider})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

if __name__ == "__main__":
    print(f"Zereos listening on 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
