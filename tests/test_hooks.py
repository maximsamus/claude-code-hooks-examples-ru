import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HooksTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-tmp').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / 'project with spaces'
        self.project.mkdir()
        (self.project / 'protected').mkdir()
        (self.project / 'src').mkdir()

    def run_hook(self, script, path='src/example.json', event=None, raw=None, **extra):
        kind = 'PreToolUse' if script == 'protect_folder.py' else 'PostToolUse'
        payload = {'hook_event_name': kind, 'tool_name': 'Write',
                   'cwd': str(self.project),
                   'tool_input': {'file_path': str(self.project / path)}}
        payload.update(extra)
        if event:
            payload['hook_event_name'] = event
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project),
                   PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-B', str(ROOT / 'hooks' / script)],
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, env=env)

    def put(self, content, path='src/example.json'):
        target = self.project / path
        target.write_text(content, encoding='utf-8')
        return target

    def test_guard_allows_source(self):
        self.assertEqual(self.run_hook('protect_folder.py').returncode, 0)

    def test_guard_denies_protected_write(self):
        result = self.run_hook('protect_folder.py', 'protected/data.json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('защищ', result.stderr)

    def test_guard_denies_protected_edit(self):
        result = self.run_hook('protect_folder.py', 'protected/data.json', tool_name='Edit')
        self.assertEqual(result.returncode, 2)
        self.assertIn('защищ', result.stderr)

    def test_guard_handles_normalized_parent(self):
        result = self.run_hook('protect_folder.py', 'src/../protected/data.json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('защищ', result.stderr)

    def test_guard_does_not_block_similar_prefix(self):
        (self.project / 'protected-copy').mkdir()
        self.assertEqual(self.run_hook('protect_folder.py', 'protected-copy/a').returncode, 0)

    def test_guard_denies_symlink_into_protected(self):
        (self.project / 'src' / 'alias').symlink_to(self.project / 'protected', target_is_directory=True)
        result = self.run_hook('protect_folder.py', 'src/alias/data.json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('защищ', result.stderr)

    def test_guard_denies_outside_project(self):
        result = self.run_hook('protect_folder.py', '../outside.json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('проект', result.stderr)

    def test_bad_input_is_not_success(self):
        for script in ('protect_folder.py', 'check_json.py', 'record_check.py'):
            with self.subTest(script=script):
                result = self.run_hook(script, raw='[]')
                self.assertEqual(result.returncode, 2)
                self.assertIn('JSON', result.stderr)

    def test_wrong_event_is_rejected(self):
        result = self.run_hook('protect_folder.py', event='PostToolUse')
        self.assertEqual(result.returncode, 2)
        self.assertIn('событи', result.stderr)

    def test_guard_does_not_claim_to_check_bash(self):
        result = self.run_hook('protect_folder.py', tool_name='Bash')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Write/Edit', result.stderr)

    def test_json_valid(self):
        self.put('{"answer": 42}\n')
        self.assertEqual(self.run_hook('check_json.py').returncode, 0)

    def test_json_invalid_is_reported_without_rewrite(self):
        target = self.put('{"answer": }\n')
        before = target.read_bytes()
        result = self.run_hook('check_json.py')
        self.assertEqual(result.returncode, 2)
        self.assertIn('JSON', result.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_json_rejects_nonstandard_nan(self):
        self.put('{"answer": NaN}\n')
        result = self.run_hook('check_json.py')
        self.assertEqual(result.returncode, 2)
        self.assertIn('JSON', result.stderr)

    def test_json_skips_other_extensions(self):
        self.put('это текст\n', 'src/note.txt')
        self.assertEqual(self.run_hook('check_json.py', 'src/note.txt').returncode, 0)

    def test_json_missing_file(self):
        result = self.run_hook('check_json.py')
        self.assertEqual(result.returncode, 2)
        self.assertIn('прочитать', result.stderr)

    def test_log_records_pass_and_fail_without_file_contents(self):
        self.put('секретное содержимое\n', 'src/note.txt')
        self.assertEqual(self.run_hook('record_check.py', 'src/note.txt').returncode, 0)
        self.put('секретное содержимое', 'src/note.txt')
        result = self.run_hook('record_check.py', 'src/note.txt')
        self.assertEqual(result.returncode, 2)
        self.assertIn('перевод', result.stderr)
        log = (self.project / '.local-checks/results.jsonl').read_text()
        rows = [json.loads(line) for line in log.splitlines()]
        self.assertEqual([row['status'] for row in rows], ['pass', 'fail'])
        self.assertEqual(rows[0]['path'], 'src/note.txt')
        self.assertNotIn('секретное', log)
        self.assertNotIn(str(self.project), log)

    def test_log_rejects_escape_without_writing(self):
        result = self.run_hook('record_check.py', '../outside.txt')
        self.assertEqual(result.returncode, 2)
        self.assertIn('проект', result.stderr)
        self.assertFalse((self.project / '.local-checks').exists())

    def test_log_rejects_symlink_directory(self):
        outside = Path(self.tmp.name) / 'other'
        outside.mkdir()
        (self.project / '.local-checks').symlink_to(outside, target_is_directory=True)
        self.put('ok\n', 'src/note.txt')
        result = self.run_hook('record_check.py', 'src/note.txt')
        self.assertEqual(result.returncode, 2)
        self.assertIn('журнал', result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_log_rejects_symlink_file(self):
        directory = self.project / '.local-checks'
        directory.mkdir()
        outside = Path(self.tmp.name) / 'untouched'
        outside.write_text('keep')
        (directory / 'results.jsonl').symlink_to(outside)
        self.put('ok\n', 'src/note.txt')
        result = self.run_hook('record_check.py', 'src/note.txt')
        self.assertEqual(result.returncode, 2)
        self.assertIn('журнал', result.stderr)
        self.assertEqual(outside.read_text(), 'keep')

    def test_settings_commands_run_as_documented(self):
        settings = json.loads((ROOT / '.claude/settings.json').read_text())
        self.assertEqual(set(settings['hooks']), {'PreToolUse', 'PostToolUse'})
        scripts = []
        for groups in settings['hooks'].values():
            for group in groups:
                self.assertEqual(group['matcher'], 'Write|Edit')
                for hook in group['hooks']:
                    self.assertEqual(hook['type'], 'command')
                    scripts.append(hook['command'])
        self.assertEqual(len(scripts), 3)

    def test_configured_commands_execute_with_space_in_project_path(self):
        shutil.copytree(ROOT / 'hooks', self.project / 'hooks')
        self.put('{"ok": true}\n')
        settings = json.loads((ROOT / '.claude/settings.json').read_text())
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        for event, groups in settings['hooks'].items():
            payload = json.dumps({'hook_event_name': event, 'tool_name': 'Write',
                                  'cwd': str(self.project), 'tool_input': {'file_path': str(self.project / 'src/example.json')}})
            for group in groups:
                for hook in group['hooks']:
                    result = subprocess.run(hook['command'], shell=True, input=payload,
                                            text=True, capture_output=True, env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_shipped_demo(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'examples/demo.py')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (ROOT / 'fixtures/expected-demo.txt').read_text())


if __name__ == '__main__':
    unittest.main()
