import json
import os

def handler(request):
    if request.method == "OPTIONS":
        return ("", 204, {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        })

    providers = []
    for name, env in [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("gemini2", "GEMINI_API_KEY2"),
        ("openai", "OPENAI_API_KEY"),
    ]:
        if os.environ.get(env):
            providers.append(name)

    return (json.dumps({"ok": True, "providers": providers}), 200, {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
    })
