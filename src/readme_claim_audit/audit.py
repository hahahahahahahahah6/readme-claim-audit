"""Filesystem-only claim extraction and reporting; never executes repository code."""
import fnmatch
import os
import re
from pathlib import Path

SKIP_DIRS = {'.git', 'node_modules', 'dist', 'build', '__pycache__', '.venv', 'venv'}
GENERIC_FLAGS = {'--help', '--version', '--json', '--verbose', '--quiet',
                 '--dry-run', '--force', '--output', '--config'}
TOOLCHAIN = {'build', 'pip', 'unittest', 'venv'}


def cap_findings(findings):
    ordered = sorted(findings, key=lambda f: (f['file'], f['line'], f['kind'], f['claim']))
    shown = []
    references = 0
    for f in ordered:
        if f['kind'] == 'dead-file-reference':
            references += 1
            if references > 20:
                continue
        if len(shown) < 500:
            shown.append(f)
    return shown, len(ordered) > len(shown)


def report(findings, ignored=0, parse_errors=0, notes=None, fail_on='high'):
    unique = {(f['file'], f['line'], f['kind'], f['claim']): f for f in findings}
    findings = list(unique.values())
    severity = {s: sum(f['severity'] == s for f in findings) for s in ('HIGH', 'MEDIUM')}
    kinds = {k: sum(f['kind'] == k for f in findings) for k in sorted({f['kind'] for f in findings})}
    verdict = 'FAIL' if severity['HIGH'] or (fail_on == 'medium' and findings) else 'WARN' if findings or parse_errors else 'PASS'
    shown, truncated = cap_findings(findings)
    return dict(verdict=verdict, total=len(findings), per_kind=kinds, per_severity=severity,
                ignored_count=ignored, parse_error_count=parse_errors, notes=notes or [],
                findings=shown, truncated=truncated, omitted_count=len(findings)-len(shown))


def audit(repo='.', ignore=(), fail_on='high'):
    root = Path(repo)
    if not root.is_dir():
        raise ValueError('repository path must be an existing directory')
    errors = []
    def read(path):
        try:
            return path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            errors.append(path)
            return ''
    entries = sorted(root.iterdir(), key=lambda p: p.name)
    readmes = [p for p in entries if p.name.lower() == 'readme.md' and p.is_file()]
    readme = next((p for p in readmes if p.name == 'README.md'), readmes[0] if readmes else None)
    project = root / 'pyproject.toml'
    metadata = read(project) if project.exists() else ''
    has_project = bool(re.search(r'^\s*\[project\]\s*$', metadata, re.M))
    section = ''
    name = version = None
    scripts = set()
    for line in metadata.splitlines():
        match = re.match(r'\s*\[([^]]+)\]', line)
        if match:
            section = match[1]
            continue
        match = re.match(r'^\s*(name|version)\s*=\s*["\']([^"\']+)["\']', line)
        if match and (section == 'project' or (not has_project and not section and match[1] == 'name')):
            if match[1] == 'name': name = match[2]
            else: version = match[2]
        if section == 'project.scripts':
            match = re.match(r'\s*["\']?([\w.-]+)["\']?\s*=', line)
            if match: scripts.add(match[1])
    flags = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(directory)/d).is_symlink())
        for filename in sorted(files):
            if filename.endswith('.py'):
                source = read(Path(directory)/filename)
                flags.update(re.findall(r'(?:add_argument|option)\(\s*["\'](--[a-z0-9][a-z0-9-]*)', source))
    makefile = next((root/n for n in ('Makefile', 'makefile') if (root/n).is_file()), None)
    targets = set()
    if makefile:
        targets = set(re.findall(r'^([A-Za-z0-9_.-]+)\s*:(?!=)', read(makefile), re.M)) - {'.PHONY'}
    findings = []
    def add(kind, claim, line, severity, snippet):
        findings.append(dict(file=readme.name if readme else '.', line=line, kind=kind,
                             claim=claim, severity=severity, detail=snippet.strip()[:120]))
    if readme is None:
        if project.exists(): add('missing-readme', 'README.md', 0, 'MEDIUM', 'Root README.md missing')
        notes = [] if project.exists() else ['not a Python package repo']
    else:
        content = read(readme)
        lines = content.splitlines()
        checked = 0
        fenced = False
        changelog = False
        changelog_level = 0
        badges, prose = [], []
        seen_names, seen_links = set(), set()
        linked = set(re.findall(r'\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)', content))
        def relative(token):
            return not token.startswith(('http://', 'https://', 'mailto:', '#', '/')) and '://' not in token
        for number, line in enumerate(lines, 1):
            heading = re.match(r'^\s*(#{1,6})\s+(.+)', line)
            if heading:
                level, title = len(heading[1]), heading[2].strip().lower()
                if changelog and level <= changelog_level: changelog = False
                if re.search(r'\bchangelog\b', title): changelog, changelog_level = True, level
            if line.lstrip().startswith('```'):
                fenced = not fenced
                continue
            code = fenced or line.startswith('    ')
            for match in re.finditer(r'\b(?:pip3?|uv\s+pip)\s+install\s+([A-Za-z0-9][A-Za-z0-9_.-]*)', line):
                claim = match[1]; checked += 1
                if name and claim != name and claim not in seen_names:
                    add('install-name-mismatch', claim, number, 'HIGH', line); seen_names.add(claim)
            for target in re.findall(r'\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)', line):
                checked += 1
                if relative(target) and target not in seen_links and not (root/target.split('#')[0]).exists():
                    add('dead-internal-link', target, number, 'HIGH', line); seen_links.add(target)
            for token in re.findall(r'(?<!`)`([^`\n]+)`(?!`)', line):
                if (relative(token) and token not in linked and not token.startswith('-')
                    and not re.search(r'pip|python|\s', token)
                    and (token in {'Makefile', 'pyproject.toml', 'LICENSE'} or ('/' in token and re.search(r'\.[\w-]+$', token)))):
                    checked += 1
                    if not (root/token).exists(): add('dead-file-reference', token, number, 'MEDIUM', line)
            if not changelog:
                for match in re.finditer(r'(?:version[-_/]|\bv)(\d+\.\d+\.\d+)(?=[-_/?.#]|\b)', line, re.I):
                    if re.search(r'https?://', line): badges.append((match[1], number, line)); checked += 1
                match = re.search(r'\bversion\s*[:=]?\s+v?(\d+\.\d+\.\d+)\b', line, re.I)
                if match: prose.append((match[1], number, line)); checked += 1
            if code:
                for flag in re.findall(r'(?<![\w-])--[a-z0-9][a-z0-9-]*', line):
                    checked += 1
                    if flag not in flags | GENERIC_FLAGS: add('documented-flag-missing', flag, number, 'HIGH', line)
                command = line.strip()
                match = re.match(r'^make\s+([A-Za-z0-9_.-]+)', command)
                if match:
                    checked += 1
                    if makefile and match[1] not in targets: add('make-target-missing', match[1], number, 'HIGH', line)
                match = re.match(r'^python3?\s+-m\s+([a-z_][a-z0-9_.]*)', command)
                if match:
                    checked += 1
                    module = match[1]; path = module.replace('.', '/')
                    if module not in TOOLCHAIN and not any((root/candidate).is_file() for candidate in
                        (path+'.py', 'src/'+path+'.py', path+'/__init__.py', 'src/'+path+'/__init__.py')):
                        add('command-path-missing', module, number, 'MEDIUM', line)
        versions = badges + prose
        if version and versions and versions[0][0] != version:
            claim, number, snippet = versions[0]
            add('version-mismatch', claim, number, 'MEDIUM', snippet)
        notes = [] if checked or errors else ['no checkable claims found']
    unique = {(f['file'], f['line'], f['kind'], f['claim']): f for f in findings}
    kept, ignored = [], 0
    for f in unique.values():
        if any(fnmatch.fnmatchcase(f['claim'], pattern) for pattern in ignore): ignored += 1
        else: kept.append(f)
    return report(kept, ignored, len(errors), notes, fail_on)
