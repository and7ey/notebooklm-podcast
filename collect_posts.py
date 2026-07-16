import json
import subprocess
import requests
import os
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

    # слишком короткие сообщения
    if len(text) < 200:
        return False


    # приветствие канала
    skip_patterns = [
        "Вступайте в ряды Фурье!",
        "То, что вы пропустили про современную науку",
        "Канал ведут",
        "По сотрудничеству"
    ]


    for pattern in skip_patterns:

        if pattern in text:
            return False


    return True

def get_post(channel, post_id):

    url = f"https://t.me/{channel}/{post_id}"

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


    description = soup.find(
        "meta",
        property="og:description"
    )


    if not description:
        return None


    text = description.get(
        "content",
        ""
    ).strip()


    if not is_content_post(soup):
        return None


    return {
        "id": post_id,
        "url": url,
        "text": text
    }



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


    notebook_json = json.loads(
        notebook
    )


    notebook_id = notebook_json[
        "notebook"
    ][
        "id"
    ]


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


    audio_result = run_command([
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


    return json.loads(
        audio_result
    )["url"]



def send_to_telegram(audio_url):

    audio = requests.get(
        audio_url,
        timeout=60
    )


    audio.raise_for_status()


    filename = "/tmp/podcast.mp3"


    Path(filename).write_bytes(
        audio.content
    )


    with open(
        filename,
        "rb"
    ) as f:

        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio",
            data={
                "chat_id": TELEGRAM_CHAT_ID
            },
            files={
                "audio": f
            },
            timeout=120
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

    audio_url = generate_podcast(
        post
    )


    send_to_telegram(
        audio_url
    )


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