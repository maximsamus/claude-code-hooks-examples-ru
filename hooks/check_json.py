"""PostToolUse: проверить JSON после правки, не менять файл."""
import json
import sys
from common import read_event, read_small, run


def reject_constant(_value):
    raise ValueError('JSON не допускает NaN и Infinity')


def check():
    _root, lexical, target = read_event('PostToolUse')
    if lexical.suffix.lower() != '.json':
        return 0
    json.loads(read_small(target), parse_constant=reject_constant)
    return 0


if __name__ == '__main__':
    sys.exit(run(check))
