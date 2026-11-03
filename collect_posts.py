import hashlib
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
TELEGRAM_CHAT_ID = "-1003960308699"  # os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_THREAD_ID = "3"


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


def get_text_hash(text):
    # Различия в пробелах и переносах не считаем новым содержимым.
    normalized = " ".join(text.split())

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def is_content_post(post):
    text = post["text"].strip()

    print("=" * 80)
    print(f"POST {post['id']}")
    print("=" * 80)
    print(text)
    print("=" * 80)

    # Пустой или слишком короткий пост.
    if len(text) < 200:
        return False

    # Настоящий приветственный пост канала.
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

    # Удаляем хвост, если он присутствует в извлечённом тексте.
    marker = "\n--\nВступайте в ряды Фурье!"

    if marker in text:
        text = text.split(marker, 1)[0].strip()

    return {
        "id": post_id,
        "url": f"https://t.me/{channel}/{post_id}",
        "text": text
    }


def find_next_post(channel, last_id, processed_hashes):
    last_skipped_id = last_id

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

        if not post or not is_content_post(post):
            continue

        text_hash = get_text_hash(post["text"])

        if text_hash in processed_hashes:
            print(
                f"Skipping duplicate text: post {post_id}",
                flush=True
            )

            last_skipped_id = post_id
            continue

        post["text_hash"] = text_hash

        return post, last_skipped_id

    return None, last_skipped_id


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
        (
            "Сделай информационный подкаст на русском языке, "
            "перепроверь правильность ударений. "
            "В начале подкаста добавь приветствие."
        ),
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

    output = run_command([
        "notebooklm",
        "download",
        "audio",
        filename,
        "-n",
        notebook_id
    ])

    size = Path(filename).stat().st_size

    m = re.search(
        r"Artifact:\s*(.*?)\s*\(only artifact\)",
        output
    )

    title = (
        m.group(1)
        if m
        else f"Ряды Фурье #{post['id']}"
    )

    print(f"Downloaded {filename}")
    print(f"Size: {size:,} bytes")

    if size < 100_000:
        raise Exception(
            "Downloaded audio is suspiciously small"
        )

    tagged = filename.replace(
        "-notags.m4a",
        ".m4a"
    )

    run_command([
        "ffmpeg",
        "-y",
        "-i",
        filename,
        "-c",
        "copy",
        "-metadata",
        "artist=Ряды Фурье",
        "-metadata",
        f"title={title}",
        "-metadata",
        "album=Подкасты NotebookLM",
        tagged
    ])

    filename = tagged

    return filename, title, notebook_id


def send_to_telegram(filename, title, post):
    with open(filename, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": (
                    f"🎙 Ряды Фурье #{post['id']}\n"
                    f"{title}"
                    f"{post['url']}"
                ),
                "title": title,
                "performer": "Ряды Фурье",
                "message_thread_id": TELEGRAM_THREAD_ID
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
    config = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)

    channel = config["channels"][0]["name"]
    channel_state = state[channel]

    last_id = channel_state["last_processed_id"]

    processed_hashes = set(
        channel_state.get(
            "processed_text_hashes",
            []
        )
    )

    post, last_skipped_id = find_next_post(
        channel,
        last_id,
        processed_hashes
    )

    if not post:
        # Сохраняем продвижение по найденным дублям,
        # даже если нового текста в окне поиска нет.
        if last_skipped_id > last_id:
            channel_state["last_processed_id"] = last_skipped_id

            channel_state["last_run"] = datetime.now(
                timezone.utc
            ).isoformat()

            save_json(
                STATE_FILE,
                state
            )

        print("No new posts")
        return

    print(
        "Found post",
        post["id"]
    )

    # До успешной отправки новый текст не отмечаем обработанным.
    filename, title, notebook_id = generate_podcast(post)

    send_to_telegram(
        filename,
        title,
        post
    )

    # Только после успешной отправки сохраняем ID и хеш текста.
    processed_hashes.add(
        post["text_hash"]
    )

    channel_state["last_processed_id"] = post["id"]

    channel_state["processed_text_hashes"] = sorted(
        processed_hashes
    )

    channel_state["last_run"] = datetime.now(
        timezone.utc
    ).isoformat()

    save_json(
        STATE_FILE,
        state
    )

    # Ошибка удаления notebook не должна помешать workflow
    # закоммитить state уже отправленного подкаста.
    try:
        run_command([
            "notebooklm",
            "delete",
            "-n",
            notebook_id,
            "-y"
        ])
    except Exception as exc:
        print(
            f"WARNING: podcast sent and state saved, "
            f"but notebook {notebook_id} could not be deleted: {exc}",
            flush=True
        )

    print("Completed successfully")


if __name__ == "__main__":
    main()
