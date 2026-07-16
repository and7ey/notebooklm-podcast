import subprocess
import json
import requests
import os
import tempfile


def run(cmd):
    print("\n$", " ".join(str(x) for x in cmd), flush=True)

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=True
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.stderr:
        print(result.stderr, flush=True)

    return result.stdout


TEXT = """
Это тест автоматической генерации подкаста.

NotebookLM создал этот аудиофайл
через GitHub Actions.
"""


# Создаем notebook

output = run([
    "notebooklm",
    "create",
    "Temporary Podcast",
    "--json"
])

data = json.loads(output)

notebook_id = data["notebook"]["id"]

print("Notebook:", notebook_id, flush=True)


# Добавляем текст

run([
    "notebooklm",
    "source",
    "add",
    TEXT,
    "--type",
    "text",
    "--title",
    "Source",
    "-n",
    notebook_id
])


# Генерируем аудио

output = run([
    "notebooklm",
    "generate",
    "audio",
    "Сделай спокойный подкаст на русском языке",
    "-n",
    notebook_id,
    "--language",
    "ru",
    "--format",
    "deep-dive",
    "--length",
    "short",
    "--wait",
    "--json"
])


audio_url = json.loads(output)["url"]

print("Audio URL:", audio_url, flush=True)


# Скачиваем mp3

audio_file = "/tmp/podcast.mp3"

r = requests.get(audio_url)

r.raise_for_status()

with open(audio_file, "wb") as f:
    f.write(r.content)


print("Downloaded:", audio_file, flush=True)


# Отправляем Telegram

token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]


with open(audio_file, "rb") as f:

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendAudio",
        data={
            "chat_id": chat_id,
            "title": "NotebookLM Podcast"
        },
        files={
            "audio": f
        }
    )


response.raise_for_status()

print("Sent to Telegram", flush=True)