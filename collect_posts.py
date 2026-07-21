import json
import subprocess
import requests
import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime, timezone


CONFIG_FILE = Path("config.json")
STATE_FILE = Path("data/state.json")


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def load_json(path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def is_content_post(post):

    text = post["text"].strip()

    print("=" * 80)
    print(f"POST {post['id']}")
    print("=" * 80)
    print(text)
    print("=" * 80)

    # пустой пост
    if not text:
        return False

    # слишком короткий
    if len(text) < 200:
        return False

    # настоящий приветственный пост канала
    if text.startswith("Вступайте в ряды Фурье!"):
        return False

    return True

def get_post(channel, post_id):

    url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"

    r = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    message = soup.find(
        "div",
        class_="tgme_widget_message_text"
    )

    if not message:
        return None

    text = message.get_text(
        "\n",
        strip=True
    )

    if not text:
        return None

    # ------------------------------------------------------------------
    # Telegram автоматически добавляет в embed рекламный блок:
    #
    # --
    # Вступайте в ряды Фурье!
    # Лучшие посты...
    #
    # Он не относится к самому посту.
    # ------------------------------------------------------------------

    marker = "\n--\nВступайте в ряды Фурье!"

    if marker in text:
        text = text.split(marker, 1)[0].strip()

    return {
        "id": post_id,
        "url": f"https://t.me/{channel}/{post_id}",
        "text": text
    }


def is_content_post(post):

    text = post["text"].strip()

    print("=" * 80)
    print(f"POST {post['id']}")
    print("=" * 80)
    print(text)
    print("=" * 80)

    # пустой пост
    if not text:
        return False

    # слишком короткий
    if len(text) < 200:
        return False

    # настоящий приветственный пост канала
    if text.startswith("Вступайте в ряды Фурье!"):
        return False

    return True



def find_next_post(channel, last_id):

    for post_id in range(
        last_id + 1,
        last_id + 7
    ):

        print(
            "Checking",
            post_id,
            flush=True
        )

        post = get_post(
            channel,
            post_id
        )

        if post and is_content_post(post):
            return post


    return None


def run_command(cmd):

    print(
        "$",
        " ".join(cmd),
        flush=True
    )


    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


    if result.stdout:
        print(
            result.stdout,
            flush=True
        )


    if result.stderr:
        print(
            result.stderr,
            flush=True
        )


    if result.returncode != 0:
        raise Exception(
            f"Command failed: {cmd}"
        )


    return result.stdout


def generate_podcast(post):

    notebook = run_command([
        "notebooklm",
        "create",
        f"Podcast {post['id']}",
        "--json"
    ])

    notebook_json = json.loads(notebook)

    notebook_id = notebook_json["notebook"]["id"]

    run_command([
        "notebooklm",
        "source",
        "add",
        post["text"],
        "--type",
        "text",
        "--title",
        f"Telegram post {post['id']}",
        "-n",
        notebook_id
    ])

    run_command([
        "notebooklm",
        "generate",
        "audio",
        "Сделай спокойный информационный подкаст на русском языке",
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

    filename = f"/tmp/podcast-{post['id']}-notags.m4a"

    run_command([
        "notebooklm",
        "download",
        "audio",
        filename,
        "-n",
        notebook_id
    ])

    size = Path(filename).stat().st_size

    m = re.search(r"Artifact:\s*(.*?)\s*\(only artifact\)", output)
    title = m.group(1) if m else f"Ряды Фурье #{post['id']}"

    print(f"Downloaded {filename}")
    print(f"Size: {size:,} bytes")

    if size < 100_000:
        raise Exception("Downloaded audio is suspiciously small")

    tagged = filename.replace("-notags.m4a", ".m4a")

    run_command([
        "ffmpeg",
        "-y",
        "-i", filename,
        "-c", "copy",
        "-metadata", "artist=Ряды Фурье",
        "-metadata", f"title={title}",
        "-metadata", "album=Подкасты NotebookLM",
        tagged
    ])

    filename = tagged        

    return filename


def send_to_telegram(filename, post):

    with open(filename, "rb") as f:

        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": f"🎙 Ряды Фурье #{post['id']}\n{post['url']}"
            },
            files={
                "audio": (
                    Path(filename).name,
                    f,
                    "audio/mp4"
                )
            },
            timeout=300
        )

    r.raise_for_status()



def main():

    config = load_json(
        CONFIG_FILE
    )

    state = load_json(
        STATE_FILE
    )


    channel = config[
        "channels"
    ][0][
        "name"
    ]


    last_id = state[channel][
        "last_processed_id"
    ]


    post = find_next_post(
        channel,
        last_id
    )


    if not post:

        print(
            "No new posts"
        )

        return


    print(
        "Found post",
        post["id"]
    )


    # пока state НЕ меняем

    filename = generate_podcast(post)

    send_to_telegram(filename, post)


    # только после успеха

    state[channel][
        "last_processed_id"
    ] = post["id"]


    state[channel][
        "last_run"
    ] = datetime.now(
        timezone.utc
    ).isoformat()


    save_json(
        STATE_FILE,
        state
    )


    print(
        "Completed successfully"
    )


if __name__ == "__main__":
    main()
