"""Sign a Windows release manifest using the private key supplied by the release job."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import __version__
from engine.update_key import PUBLIC_KEY
from engine.updater import MAX_DOWNLOAD, REPOSITORY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--installer', required=True, type=Path)
    parser.add_argument('--notes', required=True, type=Path)
    args = parser.parse_args()
    version, installer = args.version, args.installer
    if version != __version__ or installer.name != f'carkit-{version}-setup.exe':
        parser.error('Version and installer filename must match the application version.')
    try:
        key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(
            os.environ.get('CARKIT_UPDATE_SIGNING_KEY', ''), validate=True))
    except ValueError:
        parser.error('CARKIT_UPDATE_SIGNING_KEY must contain a base64 Ed25519 private key.')
    if key.public_key().public_bytes_raw() != PUBLIC_KEY:
        parser.error('Signing key does not match the trusted public key in carkit.')
    with installer.open('rb') as f:
        size = os.fstat(f.fileno()).st_size
        if not 0 < size <= MAX_DOWNLOAD or f.read(2) != b'MZ':
            parser.error('Installer is not a supported Windows executable.')
        f.seek(0)
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    manifest = json.dumps({
        'version': version,
        'notes': args.notes.read_text(encoding='utf-8'),
        'windows-x64': {
            'url': f'https://github.com/{REPOSITORY}/releases/download/v{version}/{installer.name}',
            'size': size,
            'sha256': digest,
        },
    }, ensure_ascii=False, indent=2).encode('utf-8')
    if len(manifest) > 2 * 1024 * 1024:
        parser.error('Update manifest exceeds the client size limit.')
    installer.with_name('latest.json').write_bytes(manifest)
    installer.with_name('latest.json.sig').write_bytes(key.sign(manifest))


if __name__ == '__main__':
    main()
