"""Network-free behavior checks for the optional example handoff builder."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
RELATIVE = Path('examples/agents-sdk-regression/replay')


class ReplayPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # macOS's system temp path traverses /var -> /private/var. Use its
        # physical path so fixtures comply with the unchanged no-symlink policy.
        self.root = Path(self.temporary.name).resolve()

    def command(self, *args, cwd=REPO, input=None):
        return subprocess.run(args, cwd=cwd, input=input, capture_output=True, text=True, timeout=30)

    def build(self, repo=REPO, filename='replay.tar.gz'):
        path = self.root / filename
        result = self.command(sys.executable, '-I', '-B', str(repo / RELATIVE / 'build.py'),
                              '--output', str(path), cwd=repo)
        return result, path

    def copy_checkout(self):
        target = self.root / 'checkout'
        result = self.command('git', 'clone', '--quiet', '--no-hardlinks', str(REPO), str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        # Only the reviewed replay sources are overlaid, not task evidence or outputs.
        shutil.rmtree(target / RELATIVE, ignore_errors=True)
        shutil.copytree(REPO / RELATIVE, target / RELATIVE)
        return target

    def unpack(self, archive):
        target = self.root / 'extracted'
        target.mkdir()
        with tarfile.open(archive) as tar:
            for entry in tar.getmembers():
                self.assertTrue(entry.isfile())
                self.assertNotIn('..', Path(entry.name).parts)
                self.assertFalse(Path(entry.name).is_absolute())
                local = target / entry.name
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(tar.extractfile(entry).read())
        return target / 'fanout-check-replay'

    def test_deterministic_build_and_baseline_preservation(self):
        first, one = self.build(filename='one.tar.gz')
        second, two = self.build(filename='two.tar.gz')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(one.read_bytes(), two.read_bytes())
        report = json.loads(first.stdout)
        self.assertEqual(hashlib.sha256(one.read_bytes()).hexdigest(), report['sha256'])
        root = self.unpack(one)
        for folder in ('inputs', 'expected'):
            for original in (REPO / RELATIVE / folder).glob('*.json'):
                self.assertEqual(original.read_bytes().replace(b'\r\n', b'\n'),
                                 (root / folder / original.name).read_bytes())
        runner = runpy.run_path(str(root / 'replay.py'), run_name='reviewed_replay')
        runner['integrity'](root)
        self.assertEqual(runner['COMMIT'], self.command('git', 'rev-parse', 'HEAD').stdout.strip())
        self.assertEqual(runner['ORACLE_COMMIT'], 'e03b9cf6eeb701505f2e714b4ac943ff3c67bf19')

    def test_current_head_is_used_without_changing_historical_oracle(self):
        repo = self.copy_checkout()
        tree = self.command('git', 'rev-parse', 'HEAD^{tree}', cwd=repo).stdout.strip()
        # A clearly synthetic disposable local commit, never published.
        new = self.command('git', '-c', 'user.name=Replay test fixture',
                           '-c', 'user.email=replay-test@example.invalid',
                           'commit-tree', tree, '-p', 'HEAD', cwd=repo,
                           input='Synthetic local packaging test revision\n')
        self.assertEqual(new.returncode, 0, new.stderr)
        head = new.stdout.strip()
        self.assertEqual(self.command('git', 'update-ref', 'HEAD', head, cwd=repo).returncode, 0)
        result, archive = self.build(repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        root = self.unpack(archive)
        manifest = json.loads((root / 'manifest.json').read_text())
        self.assertEqual(manifest['source_commit'], head)
        self.assertNotEqual(head, manifest['oracle_source_commit'])
        self.assertEqual((root / 'expected/summary.json').read_bytes(),
                         (REPO / RELATIVE / 'expected/summary.json').read_bytes().replace(b'\r\n', b'\n'))

    def test_crlf_checkout_preserves_exact_original_fixtures(self):
        repo = self.copy_checkout()
        # Simulate Git's ordinary CRLF worktree text without touching the
        # committed blobs; the independent review also uses real autocrlf Git.
        selected = ['LICENSE', 'README.md', 'pyproject.toml']
        selected += self.command('git', 'ls-files', 'fanout_check',
                                 'examples/agents-sdk-regression', cwd=repo).stdout.splitlines()
        selected += [p.relative_to(repo).as_posix() for p in (repo / RELATIVE).rglob('*') if p.is_file()]
        for name in set(selected):
            path = repo / name
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        result, archive = self.build(repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        root = self.unpack(archive)
        expected = (root / 'expected/summary.json').read_bytes()
        self.assertEqual(hashlib.sha256(expected).hexdigest(),
                         'd6a69f24cb10af3c6c28a7696a8b1630ad50e4a60e8e78dc9505e8c035363794')

    def test_dirty_selected_source_is_rejected(self):
        repo = self.copy_checkout()
        with (repo / 'fanout_check/core.py').open('a') as stream:
            stream.write('\n# uncommitted source\n')
        result, archive = self.build(repo)
        self.assertEqual(result.returncode, 2)
        self.assertIn('differs from HEAD', result.stderr)
        self.assertFalse(archive.exists())

    def test_changed_original_input_is_rejected(self):
        repo = self.copy_checkout()
        with (repo / RELATIVE / 'inputs/070-sync_parallel.trace.json').open('a') as stream:
            stream.write(' ')
        result, archive = self.build(repo)
        self.assertEqual(result.returncode, 2)
        self.assertIn('baseline fixtures changed', result.stderr)
        self.assertFalse(archive.exists())

    def test_undeclared_replay_code_is_rejected(self):
        repo = self.copy_checkout()
        (repo / RELATIVE / 'pip.py').write_text('raise RuntimeError("must not execute")\n')
        result, archive = self.build(repo)
        self.assertEqual(result.returncode, 2)
        self.assertIn('undeclared replay input', result.stderr)
        self.assertFalse(archive.exists())

    def test_fixture_symlink_is_rejected(self):
        repo = self.copy_checkout()
        fixture = repo / RELATIVE / 'expected/summary.json'
        original = fixture.read_bytes()
        fixture.unlink()
        target = self.root / 'external.json'
        target.write_bytes(original)
        try:
            fixture.symlink_to(target)
        except OSError as error:
            self.skipTest('symlink creation unavailable: ' + str(error))
        result, archive = self.build(repo)
        self.assertEqual(result.returncode, 2)
        self.assertIn('symlink', result.stderr)
        self.assertFalse(archive.exists())

    def test_system_temp_alias_uses_physical_workspace_without_relaxing_output_policy(self):
        alias = self.root / 'system-temp-alias'
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest('symlink creation unavailable: ' + str(error))
        # Explicit symlinked output remains rejected by the builder.
        rejected = self.command(sys.executable, '-I', '-B', str(REPO / RELATIVE / 'build.py'),
                                '--output', str(alias / 'unsafe.tar.gz'))
        self.assertEqual(rejected.returncode, 2)
        self.assertIn('symlink in output path', rejected.stderr)
        self.assertFalse((self.root / 'unsafe.tar.gz').exists())
        # The same system temp alias is harmless when the test fixture chooses
        # its physical owned directory before invoking any packaging command.
        code = ('import sys,tempfile,unittest;sys.path.insert(0,sys.argv[1]);'
                'tempfile.tempdir=sys.argv[2];'
                'suite=unittest.defaultTestLoader.loadTestsFromName('
                '"test_replay_package.ReplayPackageTests.test_deterministic_build_and_baseline_preservation");'
                'result=unittest.TextTestRunner(verbosity=2).run(suite);'
                'sys.exit(not result.wasSuccessful())')
        accepted = self.command(sys.executable, '-I', '-B', '-c', code,
                                str(REPO / 'tests'), str(alias))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_generated_replay_rejects_rehashed_source_with_unchanged_script(self):
        result, archive = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        root = self.unpack(archive)
        runner = runpy.run_path(str(root / 'replay.py'), run_name='reviewed_replay')
        source = root / 'source/fanout_check/core.py'
        source.write_bytes(source.read_bytes() + b'\n# altered source\n')
        manifest_path = root / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['sha256']['source/fanout_check/core.py'] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest) + '\n')
        with self.assertRaisesRegex(runner['ReplayError'], 'changed manifest'):
            runner['integrity'](root)
        self.assertFalse((root / '.replay').exists())
        self.assertFalse((root / 'output').exists())
