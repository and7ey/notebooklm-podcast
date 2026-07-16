import subprocess
import json
import os
import tempfile


def run(cmd):
    print("\n$", " ".join(str(x) for x in cmd))

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=True
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    return result.stdout


# Тестовый текст
text = """
Объясни основные события дня в формате подкаста.
Это тест автоматической генерации аудио через NotebookLM
из GitHub Actions.
"""


# 1. Создаем временный notebook
output = run([
    "notebooklm",
    "create",
    "GitHub Podcast Test",
    "--json"
])

data = json.loads(output)

notebook_id = data["notebook"]["id"]

print("Notebook ID:", notebook_id)


# 2. Добавляем текстовый источник
run([
    "notebooklm",
    "source",
    "add",
    text,
    "--type",
    "text",
    "--title",
    "Input text",
    "-n",
    notebook_id
])


# 3. Генерируем аудио
run([
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