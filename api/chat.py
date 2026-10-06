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

# Keep each provider fast so fallback stays responsive.
REQUEST_TIMEOUT = 8

def post_json(url, payload, headers=None, timeout=REQUEST_TIMEOUT):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as e:
        # Log only the provider response body; never log credentials.
        try:
            detail = e.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            detail = ""
        raise RuntimeError(f"HTTP {e.code}: {detail}")
    except URLError as e:
        raise RuntimeError(f"Connection error: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Request error: {type(e).__name__}: {e}")

def openai_compatible(provider, key, messages, model=None):
    if provider == "openai":
        base = "https://api.openai.com/v1/chat/completions"
        default = "gpt-4o-mini"
    else:
        base = "https://api.deepseek.com/chat/completions"
        default = "deepseek-chat"

    payload = {
        "model": model or default,
        "messages": messages,
        "temperature": 0.7,
    }
    data = post_json(base, payload, {"Authorization": f"Bearer {key}"})
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Provider returned no choices")
    text = choices[0].get("message", {}).get("content")
    if not text:
        raise RuntimeError("Provider returned an empty response")
    return str(text)

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
    data = post_json(url, {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
        },
    })

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(p.get("text", "")) for p in parts if p.get("text"))
    if not text:
        raise RuntimeError("Gemini returned an empty response")
    return text

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

    messages.append({"role": "user", "content": str(message)[:12000]})

    available = [
        name for name, env in PROVIDERS
        if os.environ.get(env, "").strip()
    ]

    if requested_provider and requested_provider in available:
        order = [requested_provider] + [
            x for x in available if x != requested_provider
        ]
    else:
        order = available

    env_map = dict(PROVIDERS)
    failures = []

    for provider in order:
        key = os.environ.get(env_map[provider], "").strip()
        if not key:
            continue

        # If the caller explicitly supplied a model, honor it.
        # Otherwise use stable current defaults, with a model fallback for Gemini.
        models = [requested_model] if requested_model else []
        if provider.startswith("gemini"):
            if not models:
                models = (
                    ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
                )
        else:
            if not models:
                models = [None]

        for model in models:
            try:
                if provider.startswith("gemini"):
                    reply = gemini(key, messages, model)
                else:
                    reply = openai_compatible(provider, key, messages, model)

                return reply, provider
            except Exception as exc:
                failure = f"{provider}/{model or 'default'}: {exc}"
                failures.append(failure)
                print(f"[zereos] {failure}")

    if not available:
        raise RuntimeError("لم يتم إعداد أي مزود ذكاء اصطناعي على الخادم.")

    raise RuntimeError(
        "تعذر الحصول على رد من مزودي الذكاء الاصطناعي المتاحين."
    )

def json_response(payload, status):
    return (
        json.dumps(payload, ensure_ascii=False),
        status,
        {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
    )

def handler(request):
    if request.method == "OPTIONS":
        return ("", 204, {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        })

    if request.method != "POST":
        return json_response({"error": "Method not allowed"}, 405)

    try:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return json_response({"error": "Invalid JSON body"}, 400)

        message = str(body.get("message", "")).strip()
        if not message:
            return json_response({"error": "Message is required"}, 400)

        reply, provider = ask(
            message,
            body.get("history", []),
            body.get("provider"),
            body.get("model"),
        )

        return json_response({
            "ok": True,
            "reply": reply,
            "provider": provider,
        }, 200)

    except Exception as e:
        print(f"[zereos] request failed: {type(e).__name__}: {e}")
        return json_response({
            "ok": False,
            "error": "تعذر الحصول على رد من مزودي الذكاء الاصطناعي المتاحين."
        }, 502)
