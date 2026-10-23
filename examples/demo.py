"""Проиграть шесть событий на фикстурах без Claude Code."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    cases = json.loads((ROOT / 'fixtures/cases.json').read_text())
    (ROOT / '.test-tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp') as temporary:
        project = Path(temporary) / 'demo project'
        shutil.copytree(ROOT / 'fixtures/project', project)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
        for case in cases:
            event = json.loads((ROOT / 'fixtures' / case['input']).read_text())
            event['cwd'] = str(project)
            event['tool_input']['file_path'] = str(project / event['tool_input']['file_path'])
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'hooks' / case['script'])],
                                    input=json.dumps(event), text=True, capture_output=True, env=env)
            if result.returncode != case['exit']:
                print('Неожиданный результат: ' + case['name'], file=sys.stderr)
                return 1
            print('{}: exit={} ({})'.format(case['name'], result.returncode, case['meaning']))
        rows = [json.loads(line) for line in (project / '.local-checks/results.jsonl').read_text().splitlines()]
        if [row['status'] for row in rows] != ['pass', 'fail']:
            print('Неверное содержимое журнала', file=sys.stderr)
            return 1
        print('Журнал: pass, fail; содержимое файлов не записано')
    return 0


if __name__ == '__main__':
    sys.exit(main())
