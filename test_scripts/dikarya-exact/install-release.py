#!/usr/bin/env python3
"""Install a verified release and optionally select it for future workers.

Requires administrator access. Never restarts services or interrupts jobs.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import tempfile


class ReleaseError(ValueError):
    pass


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path):
    """Read one regular file snapshot without following its final symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ReleaseError('Expected a regular file: ' + str(path))
        return stream.read(), info


def load_release(release):
    """Validate the manifest and retain the verified bytes that will be installed."""
    metadata_bytes, _ = read_regular(release / 'release.json')
    metadata = json.loads(metadata_bytes)
    if not isinstance(metadata, dict) or metadata.get('version') != '3.1.4-dikarya2':
        raise ReleaseError('Refusing an unexpected release version')
    if metadata.get('all_validation_passed') is not True:
        raise ReleaseError('Refusing an unvalidated release')
    files = metadata.get('files')
    if not isinstance(files, dict) or not files or 'iqtree3' not in files:
        raise ReleaseError('Release files must be a nonempty mapping containing iqtree3')
    for name, expected in files.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name)
                or name == 'release.json' or not isinstance(expected, str)
                or not re.fullmatch(r'[0-9a-f]{64}', expected)):
            raise ReleaseError('Invalid release filename or SHA-256 digest')
    snapshots = {}
    for name, expected in files.items():
        data, _ = read_regular(release / name)
        if digest_bytes(data) != expected:
            raise ReleaseError('Release checksum mismatch: ' + name)
        snapshots[name] = data
    binary = snapshots['iqtree3']
    # Validate the expected platform without ever executing package contents as
    # root. Scientific/version validation is recorded by the release builder.
    if (len(binary) < 64 or binary[:7] != b'\x7fELF\x02\x01\x01'
            or int.from_bytes(binary[16:18], 'little') not in (2, 3)
            or int.from_bytes(binary[18:20], 'little') != 62):
        raise ReleaseError('iqtree3 must be a 64-bit little-endian x86-64 ELF executable')
    return {'metadata': metadata, 'metadata_bytes': metadata_bytes, 'files': snapshots}


def ensure_directory(path, owner_uid, owner_gid, trusted_root=Path('/')):
    """Create/check a directory chain with no symlinks or writable outsiders.

    trusted_root is an internal test seam. The CLI always checks from / down.
    """
    path = Path(os.path.abspath(path))
    trusted_root = Path(os.path.abspath(trusted_root))
    if not path.is_relative_to(trusted_root):
        raise ReleaseError('Destination lies outside the trusted root')
    if path != trusted_root:
        ensure_directory(path.parent, owner_uid, owner_gid, trusted_root)
    try:
        info = path.lstat()
    except FileNotFoundError:
        if path == trusted_root:
            raise ReleaseError('Trusted root must already exist')
        path.mkdir(mode=0o755)
        os.chown(path, owner_uid, owner_gid)
        path.chmod(0o755)
        info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != owner_uid
            or stat.S_IMODE(info.st_mode) & 0o022):
        raise ReleaseError('Unsafe destination directory ownership, type or mode: ' + str(path))


def existing_regular(path, owner_uid):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid:
        raise ReleaseError('Destination must be an owned regular file, never a symlink: ' + str(path))
    return info


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_install(path, data, mode, owner_uid, owner_gid):
    existing_regular(path, owner_uid)
    descriptor, temporary = tempfile.mkstemp(prefix='.iqtree-install-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            os.fchown(stream.fileno(), owner_uid, owner_gid)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def install_release(snapshot, prefix, *, owner_uid=0, owner_gid=0, trusted_root=Path('/')):
    """Install only verified in-memory snapshots; repair matching file modes."""
    executable = prefix / 'bin/iqtree3'
    ensure_directory(executable.parent, owner_uid, owner_gid, trusted_root)
    ensure_directory(prefix / 'share', owner_uid, owner_gid, trusted_root)
    if existing_regular(executable, owner_uid) is not None:
        previous, _ = read_regular(executable)
        if digest_bytes(previous) != snapshot['metadata']['files']['iqtree3']:
            raise ReleaseError('Destination contains a different build; refusing to overwrite it')
    # Replace matching files too: a previous interruption may have left correct
    # bytes without executable permission. The old inode stays valid for jobs
    # already running while the new root-owned +0755 inode is installed.
    atomic_install(executable, snapshot['files']['iqtree3'], 0o755, owner_uid, owner_gid)
    for name, data in snapshot['files'].items():
        if name != 'iqtree3':
            atomic_install(prefix / 'share' / name, data, 0o644, owner_uid, owner_gid)
    atomic_install(prefix / 'share/release.json', snapshot['metadata_bytes'],
                   0o644, owner_uid, owner_gid)
    return executable


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def activate_environment(executable, environment, *, owner_uid=0, owner_gid=0,
                         trusted_root=Path('/')):
    """Replace exactly one setting, with a durable backup and concurrent-edit check."""
    ensure_directory(environment.parent, owner_uid, owner_gid, trusted_root)
    existing_regular(executable, owner_uid)
    binary_info = executable.lstat()
    if stat.S_IMODE(binary_info.st_mode) != 0o755:
        raise ReleaseError('Installed executable must have mode 0755')
    existing_regular(environment, owner_uid)
    original, info = read_regular(environment)
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseError('Environment file must not be writable by group or others')
    lines = original.decode('utf-8').splitlines(keepends=True)
    current = [i for i, line in enumerate(lines) if line.strip().startswith('IQTREE_BINARY=')]
    if len(current) != 1:
        raise ReleaseError('Expected exactly one active IQTREE_BINARY setting')
    index = current[0]
    ending = '\r\n' if lines[index].endswith('\r\n') else '\n' if lines[index].endswith('\n') else ''
    replacement = 'IQTREE_BINARY=' + str(executable) + ending
    if lines[index] == replacement:
        return None
    lines[index] = replacement
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = environment.with_name(environment.name + '.before-iqtree-dikarya2-' + stamp)
    backup_descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(backup_descriptor, 'wb') as stream:
        stream.write(original)
        os.fchown(stream.fileno(), info.st_uid, info.st_gid)
        os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
        stream.flush()
        os.fsync(stream.fileno())
    # Make the rollback copy durable before changing the selected executable.
    sync_directory(environment.parent)
    descriptor, temporary = tempfile.mkstemp(prefix='.iqtree2-', dir=environment.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(''.join(lines).encode('utf-8'))
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            stream.flush()
            os.fsync(stream.fileno())
        present, present_info = read_regular(environment)
        if present != original or file_identity(present_info) != file_identity(info):
            raise ReleaseError('Environment changed concurrently; selection was not updated')
        os.replace(temporary, environment)
        sync_directory(environment.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--activate', action='store_true',
                        help='Also select the installed executable for future worker starts')
    args = parser.parse_args()
    if socket.gethostname() != 'mycolab':
        raise SystemExit('This activation script is for mycolab')
    if os.geteuid() != 0:
        raise SystemExit('Installation requires administrator access')
    snapshot = load_release(args.release.resolve(strict=True))
    executable = install_release(snapshot, Path('/opt/iqtree-3.1.4-dikarya2'))
    print('Installed ' + str(executable))
    if not args.activate:
        return
    backup = activate_environment(executable, Path('/etc/dikarya/dikarya.environment.live'))
    if backup is None:
        print('IQTREE_BINARY already selects this release')
        return
    print('Selected ' + str(executable))
    print('Previous environment saved to ' + str(backup))
    print('Worker restart is pending; use the guarded Dikarya restart wrappers.')


if __name__ == '__main__':
    main()
