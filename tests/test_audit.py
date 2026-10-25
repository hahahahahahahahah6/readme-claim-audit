import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from readme_claim_audit.audit import audit, report, GENERIC_FLAGS
from readme_claim_audit.cli import main


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, path, text):
        target = self.root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def check(self, text, files=None, **kwargs):
        self.put('README.md', text)
        for name, value in (files or {}).items(): self.put(name, value)
        return audit(self.root, **kwargs)

    def test_empty(self):
        self.assertEqual(audit(self.root)['notes'], ['not a Python package repo'])

    def test_missing_readme(self):
        self.put('pyproject.toml', '')
        f = audit(self.root)['findings'][0]
        self.assertEqual((f['kind'], f['file'], f['line']), ('missing-readme', '.', 0))

    def test_missing_repo(self):
        with self.assertRaises(ValueError): audit(self.root/'absent')

    def test_invalid_utf8(self):
        (self.root/'README.md').write_bytes(b'\xff')
        r = audit(self.root)
        self.assertEqual((r['parse_error_count'], r['verdict']), (1, 'WARN'))

    def test_source_error(self):
        (self.root/'bad.py').write_bytes(b'\xff')
        self.assertEqual(audit(self.root)['parse_error_count'], 1)

    def test_ignore_once(self):
        r = self.check('    app --bad --bad', ignore=['--*', '--bad'])
        self.assertEqual((r['ignored_count'], r['total']), (1, 0))

    def test_medium_threshold(self):
        self.assertEqual(self.check('`LICENSE`', fail_on='medium')['verdict'], 'FAIL')

    def test_detail_cap(self):
        self.assertEqual(len(self.check('    app --bad '+ 'x'*200)['findings'][0]['detail']), 120)

    def test_cap(self):
        fs = [dict(file='README.md', line=i, kind='test', claim=str(i), severity='HIGH', detail='') for i in range(501)]
        r = report(fs)
        self.assertEqual((len(r['findings']), r['total'], r['omitted_count'], r['truncated']), (500, 501, 1, True))

    def test_file_cap(self):
        r = self.check('\n'.join('`docs/%s.md`' % i for i in range(25)))
        self.assertEqual((r['total'], len(r['findings']), r['omitted_count']), (25, 20, 5))

    def test_json(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(['audit', str(self.root), '--json'])
        self.assertEqual((code, json.loads(out.getvalue())['verdict']), (0, 'PASS'))

    def test_cli_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(['audit', str(self.root/'missing')])
        self.assertEqual(error.exception.code, 2)

    def test_version(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as error:
            main(['--version'])
        self.assertEqual((error.exception.code, out.getvalue().strip()), (0, '0.1.0'))

    def test_samples(self):
        samples = Path(__file__).resolve().parents[1]/'examples/sample-repo'
        self.assertEqual(audit(samples/'good')['verdict'], 'PASS')
        self.assertEqual(audit(samples/'broken')['total'], 5)
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(main(['audit', str(samples/'broken')]), 2)

    def test_preferred_readme(self):
        self.put('readme.md', '    app --bad')
        self.assertEqual(self.check('plain')['total'], 0)

    def test_case_readme(self):
        self.put('readme.MD', '    app --bad')
        self.assertEqual(audit(self.root)['findings'][0]['file'], 'readme.MD')

    def test_symlink_directory(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, 'cli.py').write_text('p.add_argument("--hidden")')
            (self.root/'linked').symlink_to(outside, target_is_directory=True)
            self.assertEqual(self.check('    app --hidden')['total'], 1)


PROJECT = {'pyproject.toml': '[project]\nname = "demo"\nversion = "0.1.0"\n'}
CASES = [
 ('plain', 'Hello', {}, 0),
 ('install', 'pip install wrong', PROJECT, 1),
 ('install_distinct', 'pip install wrong\npip3 install wrong', PROJECT, 1),
 ('install_case', 'uv pip install Demo', PROJECT, 1),
 ('install_match', 'pip install demo', PROJECT, 0),
 ('fallback', 'pip install wrong', {'pyproject.toml': 'name = "demo"'}, 1),
 ('no_fallback', 'pip install demo', {'pyproject.toml': 'name = "wrong"\n[project]\n'}, 0),
 ('flag_value', '    app --bad=value', {}, 1),
 ('flag_prose', 'app --bad', {}, 0),
 ('flag_repeat', '    app --bad --bad', {}, 1),
 ('argparse', '    app --known', {'cli.py': 'p.add_argument("--known")'}, 0),
 ('click', '```\napp --known\n```', {'cli.py': "@click.option('--known')"}, 0),
 ('link_dead', '[a](missing.md)', {}, 1),
 ('link_distinct', '[a](missing.md)\n[b](missing.md)', {}, 1),
 ('link_anchor', '[a](a.md#anchor)', {'a.md': ''}, 0),
 ('link_directory', '[a](docs)', {'docs/a.md': ''}, 0),
 ('file_dead', '`docs/a.md`', {}, 1),
 ('file_known', '`LICENSE`', {}, 1),
 ('file_exists', '`docs/a.md`', {'docs/a.md': ''}, 0),
 ('file_command', '`python docs/a.py`', {}, 0),
 ('file_url', '`https://example.invalid/a.md`', {}, 0),
 ('link_no_double', '[`docs/a.md`](docs/a.md)', {}, 1),
 ('version', 'Version 9.9.9', PROJECT, 1),
 ('version_first', 'Version 0.1.0\nversion 9.9.9', PROJECT, 0),
 ('badge_priority', 'version 9.9.9\n![v](https://example.invalid/version-0.1.0-blue)', PROJECT, 0),
 ('changelog', '## CHANGELOG\nVersion 9.9.9\n### Old\nversion 8.8.8', PROJECT, 0),
 ('after_changelog', '## Changelog\nversion 9.9.9\n## Current\nVersion 2.2.2', PROJECT, 1),
 ('make_missing', '    make absent', {'Makefile': 'test:\n'}, 1),
 ('make_exists', '    make test', {'makefile': 'test:\n'}, 0),
 ('make_assignment', '    make bad', {'Makefile': 'bad := value\n'}, 1),
 ('make_no_file', '    make absent', {}, 0),
 ('module_missing', '    python3 -m absent.mod', {}, 1),
]
for flag in sorted(GENERIC_FLAGS): CASES.append(('generic_'+flag[2:], '    app '+flag, {}, 0))
for directory in ('.git', 'node_modules', 'dist', 'build', '__pycache__', '.venv', 'venv'):
    CASES.append(('skip_'+directory, '    app --hidden', {directory+'/cli.py': 'p.add_argument("--hidden")'}, 1))
for i, path in enumerate(('a/b.py', 'src/a/b.py', 'a/b/__init__.py', 'src/a/b/__init__.py')):
    CASES.append(('module_'+str(i), '    python -m a.b', {path: ''}, 0))
for i, target in enumerate(('https://example.invalid/a', 'http://example.invalid', 'mailto:test@example.invalid', '#anchor', '/absolute', 'custom://value')):
    CASES.append(('external_'+str(i), '[link]('+target+')', {}, 0))
for module in ('build', 'pip', 'unittest', 'venv'): CASES.append(('toolchain_'+module, '    python -m '+module, {}, 0))


def make_test(text, files, total):
    def test(self): self.assertEqual(self.check(text, files)['total'], total)
    return test
for name, text, files, total in CASES:
    setattr(AuditTests, 'test_'+name.replace('-', '_').replace('.', '_'), make_test(text, files, total))
