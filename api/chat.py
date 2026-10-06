import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROVIDERS = [
    ("deepseek", "DEEPSEEK_API_KEY"),
    ("gemini", "GEMINI_API_KEY"),
    ("gemini2", "GEMINI_API_KEY2"),
    ("openai", "OPENAI_API_KEY"),
]

def post_json(url, payload, headers=None, timeout=8):
    data = json.dumps(payload).encode()
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        raise RuntimeError(f"Provider HTTP {e.code}")
    except URLError as e:
        raise RuntimeError(f"Provider connection error: {e.reason}")

def openai_compatible(provider, key, messages, model=None):
    if provider == "openai":
        base, default = "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"
    else:
        base, default = "https://api.deepseek.com/chat/completions", "deepseek-chat"
    payload = {
        "model": model or default,
        "messages": messages,
        "temperature": 0.7,
    }
    data = post_json(base, payload, {"Authorization": f"Bearer {key}"})
    return data["choices"][0]["message"]["content"]

def gemini(key, messages, model=None):
    model = model or "gemini-3.8-flash"
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": str(m["content"])}],
        })
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    data = post_json(url, {"contents": contents})
    return data["candidates"][0]["content"]["parts"][0]["text"]

def ask(message, history, requested_provider=None, requested_model=None):
    messages = [{
        "role": "system",
        "content": (
            "You are Zereos, a helpful personal AI assistant. "
            "Reply clearly and naturally. Prefer Arabic when the user writes Arabic."
        ),
    }]

    for item in (history or [])[-12:]:
        if item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({
                "role": item["role"],
                "content": str(item["content"])[:12000],
            })

    messages.append({"role": "user", "content": message})

    available = [name for name, env in PROVIDERS if os.environ.get(env)]
    if requested_provider and requested_provider in available:
        order = [requested_provider] + [x for x in available if x != requested_provider]
    else:
        order = available

    env_map = dict(PROVIDERS)
    for provider in order:
        key = os.environ.get(env_map[provider])
        try:
            if provider.startswith("gemini"):
                return gemini(key, messages, requested_model), provider
            return openai_compatible(provider, key, messages, requested_model), provider
        except Exception:
            continue

    if not available:
        raise RuntimeError("لم يتم إعداد أي مزود ذكاء اصطناعي على الخادم.")
    raise RuntimeError("تعذر الحصول على رد الآن. تمت تجربة مزودي الذكاء الاصطناعي المتاحين.")

def handler(request):
    if request.method == "OPTIONS":
        return ("", 204, {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        })

    if request.method != "POST":
        return (json.dumps({"error": "Method not allowed"}, ensure_ascii=False), 405, {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        })

    try:
        body = request.get_json(silent=True) or {}
        message = str(body.get("message", "")).strip()
        if not message:
            return (json.dumps({"error": "Message is required"}, ensure_ascii=False), 400, {
                "Content-Type": "application/json; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
            })

        reply, provider = ask(
            message,
            body.get("history", []),
            body.get("provider"),
            body.get("model"),
        )
        return (json.dumps({
            "reply": reply,
            "provider": provider,
        }, ensure_ascii=False), 200, {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        })
    except Exception as e:
        return (json.dumps({"error": str(e)}, ensure_ascii=False), 500, {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        })
