"""Общие проверки входа. Ни содержимое stdin, ни файлы не исполняются."""
import json
import os
from pathlib import Path
import sys

MAX_BYTES = 1024 * 1024


def inside(path, directory):
    return path == directory or directory in path.parents


def read_event(expected):
    raw = sys.stdin.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('JSON события слишком большой')
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError('Ожидается JSON-объект события')
    if event.get('hook_event_name') != expected:
        raise ValueError('Неверное событие хука: ожидается ' + expected)
    if event.get('tool_name') not in ('Write', 'Edit'):
        raise ValueError('Этот пример поддерживает только Write/Edit')
    project = os.environ.get('CLAUDE_PROJECT_DIR')
    if not project or not Path(project).is_absolute():
        raise ValueError('Задайте абсолютный CLAUDE_PROJECT_DIR для проекта')
    root = Path(project).resolve(strict=True)
    cwd = event.get('cwd')
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise ValueError('Нет абсолютного cwd проекта')
    cwd = Path(cwd).resolve(strict=True)
    if not inside(cwd, root):
        raise ValueError('Рабочая папка находится за пределами проекта')
    tool_input = event.get('tool_input')
    raw_path = tool_input.get('file_path') if isinstance(tool_input, dict) else None
    if not isinstance(raw_path, str) or not raw_path or '\x00' in raw_path:
        raise ValueError('Нет корректного tool_input.file_path в JSON')
    lexical = Path(os.path.abspath(cwd / raw_path))
    target = lexical.resolve()
    if not inside(lexical, root) or not inside(target, root):
        raise ValueError('Файл находится за пределами проекта')
    return root, lexical, target


def read_small(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Файл больше 1 МиБ: проверка не выполнена')
    return data.decode('utf-8')


def run(check):
    try:
        return check()
    except (OSError, ValueError, RuntimeError) as error:
        # Ошибка JSON может содержать фрагмент пользовательского файла - не печатаем его.
        if isinstance(error, json.JSONDecodeError):
            message = 'Некорректный JSON: строка {}, столбец {}'.format(error.lineno, error.colno)
        elif isinstance(error, OSError):
            message = 'Не удалось прочитать файл или записать журнал (код {})'.format(error.errno)
        else:
            message = str(error)
        print(message, file=sys.stderr)
        return 2
