"""Scan committed blobs and added lines; site-specific machine names belong in the optional untracked scripts/.public_scan_local_deny (one regex per line)."""
import argparse
import ast
import collections
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOW_FILE = 'scripts/public_scan_allow.txt'
PATTERNS = {
    'abs_path': r'/Users/|/home/|/workspace/|/root/|/private/var|/tmp/[A-Za-z0-9_.-]+|~/codex-jobs|[CD]:\\+',
    'holdout_location': r'holdout-(?:sealed|work)|(?:\bholdout\b|留出)[^\n]{0,60}(?:[/\\][\w.-]+|\b(?:dir|directory|job(?:[ _-]?id)?|host)\s*(?:[:=]\s*|\s+)[A-Za-z0-9_.-]+|\b[A-Za-z0-9_-]+\.local\b)|(?:[/\\][\w./-]+|\b(?:dir|directory|job(?:[ _-]?id)?|host)\s*(?:[:=]\s*|\s+)[A-Za-z0-9_.-]+|\b[A-Za-z0-9_-]+\.local\b)[^\n]{0,60}(?:\bholdout\b|留出)',
    'word_private': r'\bprivate\b',
    'word_hpo': r'\bhpo\b',
    'deploy_secrets': r'deploy/secrets|secrets/',
    'credential': r'AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{12,}|(?:gh[pso]_|github_pat_)[A-Za-z0-9_]{12,}|xox[abprs]-[A-Za-z0-9-]{12,}|AIza[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._~+/-]{16,}|\b(?:password|secret|api_key|access_token|refresh_token)[\s\x22\x27]*[:=]\s*[\x22\x27]?[^\s\x22\x27,;]{8,}|auth\.json',
    'private_ip': r'(?<![\d.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\d.])',
    'hostname': r'\b[A-Za-z0-9_-]+\.local\b',
}
RULES = {key: re.compile(pattern, 0 if key == 'abs_path' else re.I)
         for key, pattern in PATTERNS.items()}


def load_local_deny(path=None):
    path = ROOT / 'scripts/.public_scan_local_deny' if path is None else pathlib.Path(path)
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return ()
    return tuple(re.compile(line, re.I) for line in lines if line.strip())


def categories(line, local_deny=()):
    found = {key for key, pattern in RULES.items() if pattern.search(line)}
    if any(pattern.search(line) for pattern in local_deny):
        found.add('local_deny')
    return found


def git(*args):
    return subprocess.check_output(['git', '-c', 'core.quotePath=false', *args], cwd=ROOT)


def tree(ref):
    """Read blobs without opening worktree paths, symlink targets or credentials."""
    entries = []
    for entry in git('ls-tree', '-rz', '--full-tree', ref).split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        _mode, kind, oid = meta.split()
        if kind == b'blob':
            entries.append((path.decode('utf-8', 'replace'), oid))
        else:
            raise ValueError('Cannot inspect non-blob tree entry')
    proc = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
                          input=b''.join(oid+b'\n' for _, oid in entries),
                          stdout=subprocess.PIPE, check=True)
    offset = 0
    blobs = {}
    for path, _oid in entries:
        end = proc.stdout.index(b'\n', offset)
        size = int(proc.stdout[offset:end].split()[2])
        offset = end + 1
        blobs[path] = proc.stdout[offset:offset+size].decode('utf-8', 'replace').splitlines()
        offset += size + 1
    return blobs


def allowlist(blobs):
    allowed = {}
    for line in blobs.get(ALLOW_FILE, []):
        if not line.strip() or line.startswith('#'):
            continue
        entry, sep, reason = line.partition('  # ')
        path, number, category = entry.rsplit(':', 2)
        if not sep or not reason.strip() or category not in RULES:
            raise ValueError('Invalid allowlist entry')
        key = (path, int(number), category)
        if key in allowed:
            raise ValueError('Duplicate allowlist entry')
        allowed[key] = reason
    return allowed


def commits_from_input(lines, fallback):
    commits = set()
    tips = set()
    for line in lines:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4:
            raise ValueError('Malformed pre-push input')
        _local_ref, local, _remote_ref, remote = fields
        if not re.fullmatch(r'[0-9a-f]{40,64}', local) or not re.fullmatch(r'[0-9a-f]{40,64}', remote):
            raise ValueError('Malformed object ID')
        if set(local) == {'0'}:  # Deleting a ref introduces no content.
            continue
        tips.add(local)
        base = 'origin/main' if set(remote) == {'0'} else remote
        commits.update(git('rev-list', f'{base}..{local}').decode().splitlines())
    if not lines:
        commits.update(git('rev-list', fallback).decode().splitlines())
    return sorted(commits), tips


def added_lines(commit):
    parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
    diffs = [git('diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--text',
                 '--unified=0', parent, commit, '--') for parent in parents]
    if not parents:
        diffs = [git('show', '--format=', '--root', '--no-ext-diff', '--no-textconv',
                     '--no-renames', '--text', '--unified=0', commit, '--')]
    for diff in diffs:
        path, number = None, 0
        for line in diff.decode('utf-8', 'replace').splitlines():
            if line.startswith('diff --git '):
                path = None
            elif line.startswith('+++ ') and path is None:
                name = line[4:]
                if name.startswith('"'):
                    name = ast.literal_eval(name)
                path = name[2:] if name.startswith('b/') else None
                if path:
                    yield path, 0, path
            elif line.startswith('@@ '):
                number = int(re.search(r'\+(\d+)', line)[1])
            elif path and line.startswith('+'):
                yield path, number, line[1:]
                number += 1
            elif path and line.startswith(' '):
                number += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--range', default='origin/main..HEAD')
    parser.add_argument('--pre-push', action='store_true', help='Read Git ref updates from stdin')
    args = parser.parse_args(argv)
    try:
        local_deny = load_local_deny()
        head = tree('HEAD')
        allowed = allowlist(head)
        updates = sys.stdin.read().splitlines() if args.pre_push else []
        commits, tips = commits_from_input(updates, args.range)
        hits = set()
        for ref in {'HEAD'} | tips:
            for path, lines in (head if ref == 'HEAD' else tree(ref)).items():
                for number, line in enumerate([path] + lines):
                    hits.update((path, number, cat, line) for cat in categories(line, local_deny))
        for commit in commits:
            for path, number, line in added_lines(commit):
                hits.update((path, number, cat, line) for cat in categories(line, local_deny))
        counts, exemptions = collections.Counter(), collections.Counter()
        for path, number, category, line in sorted(hits):
            key = (path, number, category)
            current = [path] + head.get(path, [])
            # An exemption cannot conceal a different historical line at this position.
            exempt = key in allowed and 0 <= number < len(current) and current[number] == line
            (exemptions if exempt else counts)[category] += 1
            label = 'ALLOW' if exempt else 'HIT'
            # Mask the entire excerpt: other text on the line could be another secret.
            excerpt = '*' * min(24, len(line))
            safe_path = '[masked filename]' if categories(path, local_deny) else path
            print(f'{safe_path}:{number}: {category} [{label}] {excerpt}')
        for category in (*RULES, 'local_deny'):
            print(f'{category}: {counts[category]} un-allowlisted, {exemptions[category]} allowlisted')
        print(f'Scanned HEAD, {len(tips)} push tips and added lines of {len(commits)} commits.')
        print(f'Result: {sum(counts.values())} un-allowlisted hits; {sum(exemptions.values())} allowlisted hits.')
        return 1 if counts else 0
    except (ValueError, KeyError, OSError, re.error, subprocess.CalledProcessError):
        print('Scan failed: invalid input, unreadable Git objects or invalid local deny file; push blocked.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
