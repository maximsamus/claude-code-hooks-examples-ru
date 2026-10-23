"""PreToolUse: запрет Write/Edit в выбранной папке."""
import argparse
from pathlib import Path
import sys
from common import inside, read_event, run


def check():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protected', default='protected', help='Папка относительно корня проекта')
    args = parser.parse_args()
    root, lexical, target = read_event('PreToolUse')
    relative = Path(args.protected)
    if relative.is_absolute() or '..' in relative.parts or relative == Path('.'):
        raise ValueError('Защищаемая папка должна быть внутри проекта и не равняться его корню')
    folder = root / relative
    resolved_folder = folder.resolve()
    if not inside(resolved_folder, root):
        raise ValueError('Защищаемая папка ведет за пределы проекта')
    if inside(lexical, folder) or inside(target, resolved_folder):
        raise ValueError('Запись запрещена: выбрана защищенная папка')
    return 0


if __name__ == '__main__':
    sys.exit(run(check))
