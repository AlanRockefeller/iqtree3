"""Exercise installation and activation entirely inside temporary directories."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location('dikarya_installer',
                                             Path(__file__).with_name('install-release.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='iqtree-installer-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release = self.root / 'release'
        self.release.mkdir()
        # A header fixture is sufficient: the installer deliberately never
        # executes incoming binaries, including when run by an administrator.
        binary = bytearray(64)
        binary[:7] = b'\x7fELF\x02\x01\x01'
        binary[16:18] = (2).to_bytes(2, 'little')
        binary[18:20] = (62).to_bytes(2, 'little')
        self.binary = bytes(binary) + b'fixture executable bytes'
        (self.release / 'iqtree3').write_bytes(self.binary)
        (self.release / 'source.patch').write_bytes(b'fixture source patch\n')
        self.metadata = {
            'version': '3.1.4-dikarya2', 'all_validation_passed': True,
            'files': {'iqtree3': installer.digest_bytes(self.binary),
                      'source.patch': installer.digest_bytes(b'fixture source patch\n')},
        }
        self.write_metadata()
        self.prefix = self.root / 'opt/iqtree-3.1.4-dikarya2'
        self.options = {'owner_uid': os.geteuid(), 'owner_gid': os.getegid(),
                        'trusted_root': self.root}

    def write_metadata(self):
        (self.release / 'release.json').write_text(json.dumps(self.metadata))

    def install(self, snapshot=None):
        snapshot = snapshot or installer.load_release(self.release)
        return installer.install_release(snapshot, self.prefix, **self.options)

    def environment(self, data=b'OTHER=keep\nIQTREE_BINARY=/old/bin/iqtree3\nTAIL=keep\n'):
        parent = self.root / 'etc/dikarya'
        installer.ensure_directory(parent, os.geteuid(), os.getegid(), self.root)
        environment = parent / 'environment.live'
        environment.write_bytes(data)
        environment.chmod(0o600)
        return environment

    def test_strict_validation_flag_and_schema(self):
        for invalid in ('false', 'true', 1, None, False):
            with self.subTest(flag=invalid):
                self.metadata['all_validation_passed'] = invalid
                self.write_metadata()
                with self.assertRaises(installer.ReleaseError):
                    installer.load_release(self.release)
        self.metadata['all_validation_passed'] = True
        for files in ({}, [], {'source.patch': '0' * 64},
                      {'iqtree3': 'not a digest'},
                      {'iqtree3': '0' * 64, '../outside': '0' * 64}):
            with self.subTest(files=files):
                self.metadata['files'] = files
                self.write_metadata()
                with self.assertRaises(installer.ReleaseError):
                    installer.load_release(self.release)

    def test_source_checksum_and_elf_are_required(self):
        (self.release / 'iqtree3').write_bytes(b'changed')
        with self.assertRaisesRegex(installer.ReleaseError, 'checksum'):
            installer.load_release(self.release)
        self.metadata['files']['iqtree3'] = installer.digest_bytes(b'changed')
        self.write_metadata()
        with self.assertRaisesRegex(installer.ReleaseError, 'ELF'):
            installer.load_release(self.release)
        self.assertFalse(self.prefix.exists())

    def test_source_symlinks_are_rejected(self):
        source = self.release / 'iqtree3'
        source.unlink()
        outside = self.root / 'outside'
        outside.write_bytes(self.binary)
        source.symlink_to(outside)
        with self.assertRaises(OSError):
            installer.load_release(self.release)

    def test_verified_snapshot_survives_source_replacement(self):
        snapshot = installer.load_release(self.release)
        (self.release / 'iqtree3').write_bytes(b'unverified replacement')
        executable = self.install(snapshot)
        self.assertEqual(executable.read_bytes(), self.binary)
        self.assertEqual(stat.S_IMODE(executable.stat().st_mode), 0o755)
        self.assertEqual(executable.stat().st_uid, os.geteuid())
        self.assertEqual((self.prefix / 'share/source.patch').read_bytes(), b'fixture source patch\n')
        self.assertEqual(stat.S_IMODE((self.prefix / 'share/release.json').stat().st_mode), 0o644)

    def test_matching_nonexecutable_is_repaired_and_different_build_refused(self):
        executable = self.install()
        executable.chmod(0o644)
        self.install()
        self.assertEqual(stat.S_IMODE(executable.stat().st_mode), 0o755)
        executable.write_bytes(b'another build')
        with self.assertRaisesRegex(installer.ReleaseError, 'different build'):
            self.install()
        self.assertEqual(executable.read_bytes(), b'another build')

    def test_destination_symlink_and_writable_parent_are_rejected(self):
        executable = self.install()
        executable.unlink()
        victim = self.root / 'victim'
        victim.write_bytes(self.binary)
        executable.symlink_to(victim)
        with self.assertRaises(installer.ReleaseError):
            self.install()
        self.assertTrue(executable.is_symlink())
        self.assertEqual(victim.read_bytes(), self.binary)
        executable.unlink()
        executable.parent.chmod(0o777)
        with self.assertRaisesRegex(installer.ReleaseError, 'directory'):
            self.install()

    def test_symlink_directory_is_rejected(self):
        self.prefix.parent.mkdir(parents=True)
        other = self.root / 'another-prefix'
        other.mkdir()
        self.prefix.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(installer.ReleaseError, 'directory'):
            self.install()
        self.assertEqual(list(other.iterdir()), [])

    def test_interrupted_binary_replace_keeps_existing_file(self):
        executable = self.install()
        with mock.patch.object(installer.os, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(executable.read_bytes(), self.binary)
        self.assertEqual(list(executable.parent.glob('.iqtree-install-*')), [])

    def test_activation_changes_only_setting_and_preserves_protected_backup(self):
        executable = self.install()
        original = b'# IQTREE_BINARY=comment\r\nOTHER=retain exactly\r\nIQTREE_BINARY=/old\r\nTAIL=value\r\n'
        environment = self.environment(original)
        backup = installer.activate_environment(executable, environment, **self.options)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(backup.stat().st_uid, os.geteuid())
        self.assertEqual(environment.read_bytes(), original.replace(
            b'IQTREE_BINARY=/old\r\n', ('IQTREE_BINARY=' + str(executable) + '\r\n').encode()))
        self.assertEqual(stat.S_IMODE(environment.stat().st_mode), 0o600)
        self.assertIsNone(installer.activate_environment(executable, environment, **self.options))
        self.assertEqual(len(list(environment.parent.glob('*.before-*'))), 1)

    def test_duplicate_setting_is_refused_without_changes(self):
        executable = self.install()
        original = b'IQTREE_BINARY=/one\nIQTREE_BINARY=/two\n'
        environment = self.environment(original)
        with self.assertRaisesRegex(installer.ReleaseError, 'exactly one'):
            installer.activate_environment(executable, environment, **self.options)
        self.assertEqual(environment.read_bytes(), original)
        self.assertEqual(list(environment.parent.glob('*.before-*')), [])

    def test_environment_bytes_are_protected_before_final_modes_are_applied(self):
        executable = self.install()
        environment = self.environment(b'VALUE=' + b'x' * 20000 + b'\nIQTREE_BINARY=/old\n')
        modes_before_chmod = []
        chmod = installer.os.fchmod
        def inspect_mode(descriptor, mode):
            modes_before_chmod.append(stat.S_IMODE(os.fstat(descriptor).st_mode))
            chmod(descriptor, mode)
        with mock.patch.object(installer.os, 'fchmod', side_effect=inspect_mode):
            installer.activate_environment(executable, environment, **self.options)
        self.assertEqual(modes_before_chmod, [0o600, 0o600])

    def test_concurrent_edit_is_preserved_and_activation_aborted(self):
        executable = self.install()
        environment = self.environment()
        original = environment.read_bytes()
        changed = original + b'CONCURRENT_EDIT=keep\n'
        sync = installer.sync_directory
        def change_after_backup(path):
            environment.write_bytes(changed)
            sync(path)
        with mock.patch.object(installer, 'sync_directory', side_effect=change_after_backup):
            with self.assertRaisesRegex(installer.ReleaseError, 'concurrently'):
                installer.activate_environment(executable, environment, **self.options)
        self.assertEqual(environment.read_bytes(), changed)
        self.assertEqual(list(environment.parent.glob('.iqtree2-*')), [])
        backup, = environment.parent.glob('*.before-*')
        self.assertEqual(backup.read_bytes(), original)

    def test_activation_replace_failure_leaves_original_and_backup(self):
        executable = self.install()
        environment = self.environment()
        original = environment.read_bytes()
        with mock.patch.object(installer.os, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                installer.activate_environment(executable, environment, **self.options)
        self.assertEqual(environment.read_bytes(), original)
        backup, = environment.parent.glob('*.before-*')
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(list(environment.parent.glob('.iqtree2-*')), [])


if __name__ == '__main__':
    unittest.main()
