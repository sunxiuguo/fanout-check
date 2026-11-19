"""Build this example's deterministic handoff using stdlib and committed Git blobs."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).absolute().parent
REPO = HERE.parents[2]
BASELINE_COMMIT = 'e03b9cf6eeb701505f2e714b4ac943ff3c67bf19'
# Original 30 inputs and 16 expected files, sorted by relative name, separated
# as name + NUL + bytes + NUL. Build never captures or refreshes an oracle.
FIXTURES_SHA256 = 'ba9c1ceb97bf2885f2126bb027c0d88bc5ce8534e35cb572375e8f08b7e61553'
CASES = ('async_blocking', 'async_parallel', 'async_sequential',
         'capped_inside', 'sync_parallel')
SUFFIXES = ('070', '080', '0231')
SOURCE_PATHS = ('LICENSE', 'README.md', 'pyproject.toml', 'fanout_check',
                'examples/agents-sdk-regression/probe.py',
                'examples/agents-sdk-regression/constraints-historical.txt',
                'examples/agents-sdk-regression/constraints-0.23.1.txt')


class BuildError(Exception):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    result = subprocess.run(['git', '-C', str(REPO), *args],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise BuildError('Git read failed: ' + result.stderr.decode(errors='replace').strip())
    return result.stdout


def regular_file(path):
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise BuildError('symlink in selected path: ' + str(path))
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BuildError('selected file must be regular and not hard-linked: ' + str(path))
    return path.read_bytes()


def selected_source():
    if Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve() != REPO.resolve():
        raise BuildError('run the builder in its normal repository checkout')
    commit = git('rev-parse', 'HEAD').decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise BuildError('expected a SHA-1 Git source commit')
    payload, blobs = {}, {}
    entries = git('ls-tree', '-rz', '--full-tree', commit, '--', *SOURCE_PATHS)
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = raw_name.decode()
        if (mode not in ('100644', '100755') or kind != 'blob'
                or PurePosixPath(name).as_posix() != name or '\\' in name
                or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
            raise BuildError('unsafe selected Git entry')
        data = git('cat-file', 'blob', blob)
        working = regular_file(REPO / name)
        # Git's normal CRLF checkout form must not look like a source edit.
        # Still package the exact committed blob; never invoke clean/smudge hooks.
        if working != data and working.replace(b'\r\n', b'\n') != data:
            raise BuildError('selected source differs from HEAD; commit or restore it first: ' + name)
        payload['source/' + name] = data
        blobs[name] = blob
    required = {'source/' + p for p in SOURCE_PATHS if p != 'fanout_check'}
    required.add('source/fanout_check/__main__.py')
    if not required <= payload.keys():
        raise BuildError('missing selected committed source')
    return commit, payload, blobs


def replay_inputs():
    names = {'README.md', 'replay.py.in', 'build.py'}
    names.update('requirements/' + suffix + ext
                 for suffix in SUFFIXES for ext in ('.in', '.txt'))
    fixtures = {'expected/summary.json'}
    for suffix in SUFFIXES:
        for case in CASES:
            name = suffix + '-' + case
            fixtures.update(('inputs/' + name + '.trace.json',
                             'inputs/' + name + '.contract.json',
                             'expected/' + name + '.report.json'))
    names |= fixtures
    actual = set()
    for folder, dirs, files in os.walk(HERE, followlinks=False):
        for name in (*dirs, *files):
            if (Path(folder) / name).is_symlink():
                raise BuildError('symlink in replay inputs')
        actual.update((Path(folder) / name).relative_to(HERE).as_posix() for name in files)
    if actual != names:
        raise BuildError('missing or undeclared replay input')
    # These explicitly selected replay files are UTF-8 text. Restore LF bytes
    # from a normal core.autocrlf checkout, including the original fixtures.
    files = {name: regular_file(HERE / name).replace(b'\r\n', b'\n') for name in names}
    recorded = hashlib.sha256()
    for name in sorted(fixtures):
        recorded.update(name.encode() + b'\0' + files[name] + b'\0')
    if recorded.hexdigest() != FIXTURES_SHA256:
        raise BuildError('original baseline fixtures changed; build cannot refresh expectations')
    return files


def build(destination):
    commit, payload, blobs = selected_source()
    files = replay_inputs()
    payload.update((name, data) for name, data in files.items()
                   if name not in ('build.py', 'replay.py.in') and not name.endswith('.in'))
    manifest = {'source_commit': commit, 'oracle_source_commit': BASELINE_COMMIT,
                'source_git_blobs': blobs,
                'sha256': {name: sha(data) for name, data in sorted(payload.items())}}
    raw_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    template = files['replay.py.in'].decode()
    for placeholder in ('@SOURCE_COMMIT@', '@MANIFEST_SHA256@'):
        if template.count(placeholder) != 1:
            raise BuildError('unexpected replay template placeholder count')
    runner = template.replace('@SOURCE_COMMIT@', commit).replace('@MANIFEST_SHA256@', sha(raw_manifest))
    payload['manifest.json'] = raw_manifest
    payload['replay.py'] = runner.encode()
    payload['SHA256SUMS'] = ''.join(sha(data) + '  ' + name + '\n'
                                  for name, data in sorted(payload.items())).encode()
    destination = destination.absolute()
    if not destination.name.endswith('.tar.gz'):
        raise BuildError('output must end in .tar.gz')
    for parent in (destination, *destination.parents):
        if parent.is_symlink():
            raise BuildError('symlink in output path')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.replay-build-', dir=destination.parent) as temporary:
        archive = Path(temporary) / 'replay.tar.gz'
        with archive.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as tar:
                    for name, data in sorted(payload.items()):
                        info = tarfile.TarInfo('fanout-check-replay/' + name)
                        info.size, info.mode, info.mtime = len(data), 0o644, 0
                        tar.addfile(info, io.BytesIO(data))
        digest = sha(archive.read_bytes())
        os.replace(archive, destination)
    print(json.dumps({'artifact': str(destination), 'sha256': digest,
                      'bytes': destination.stat().st_size, 'files': len(payload),
                      'source_commit': commit, 'oracle_source_commit': BASELINE_COMMIT}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=REPO / 'dist/agents-sdk-replay/fanout-check-replay.tar.gz')
    args = parser.parse_args()
    try:
        build(args.output)
    except (BuildError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('BUILD FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(2)
