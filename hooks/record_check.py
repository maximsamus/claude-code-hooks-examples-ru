"""PostToolUse: проверить финальный перевод строки и записать результат."""
from datetime import datetime, timezone
import json
import os
import stat
import sys
from common import read_event, read_small, run


def append_result(root, row):
    directory = root / '.local-checks'
    if directory.is_symlink():
        raise ValueError('Папка журнала не должна быть символической ссылкой')
    directory.mkdir(exist_ok=True, mode=0o700)
    if directory.resolve() != directory:
        raise ValueError('Недопустимый путь журнала')
    path = directory / 'results.jsonl'
    if path.is_symlink():
        raise ValueError('Файл журнала не должен быть символической ссылкой')
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NONBLOCK | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.fstat(descriptor).st_nlink != 1:
            raise ValueError('Журнал должен быть обычным файлом без жестких ссылок')
        payload = (json.dumps(row, ensure_ascii=False) + '\n').encode('utf-8')
        if os.write(descriptor, payload) != len(payload):
            raise ValueError('Не удалось полностью записать журнал')
    finally:
        os.close(descriptor)


def check():
    root, lexical, target = read_event('PostToolUse')
    if lexical.suffix.lower() not in ('.txt', '.md', '.py', '.json'):
        return 0
    text = read_small(target)
    passed = not text or text.endswith('\n')
    append_result(root, {
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'path': lexical.relative_to(root).as_posix(),
        'check': 'final_newline',
        'status': 'pass' if passed else 'fail',
    })
    if not passed:
        raise ValueError('Проверка не пройдена: добавьте перевод строки в конце файла')
    return 0


if __name__ == '__main__':
    sys.exit(run(check))
