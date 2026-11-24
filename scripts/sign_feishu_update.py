"""Sign the package inventory published as attachments in the Feishu update document."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.update_key import PUBLIC_KEY
from engine.updater import MAX_DOWNLOAD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--assets', required=True, type=Path)
    parser.add_argument('--notes', required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}', args.version):
        parser.error('A three-part release version is required.')
    try:
        key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(
            os.environ.get('CARKIT_UPDATE_SIGNING_KEY', ''), validate=True))
    except ValueError:
        parser.error('CARKIT_UPDATE_SIGNING_KEY must contain a base64 Ed25519 private key.')
    if key.public_key().public_bytes_raw() != PUBLIC_KEY:
        parser.error('Signing key does not match the trusted application key.')
    version = args.version
    names = {
        'windows-installer': f'carkit-{version}-setup.exe',
        'windows-x64': f'carkit-{version}.exe',
        'macos-arm64': f'carkit-{version}-macos-arm64.dmg',
    }
    packages = {}
    for target, name in names.items():
        with (args.assets / name).open('rb') as source:
            size = os.fstat(source.fileno()).st_size
            if not 0 < size <= MAX_DOWNLOAD:
                parser.error(f'Invalid package size: {name}')
            if target.startswith('windows-') and source.read(2) != b'MZ':
                parser.error(f'Not a Windows executable: {name}')
            source.seek(0)
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        packages[target] = {'name': name, 'size': size, 'sha256': digest}
    raw = json.dumps({'version': version, 'notes': args.notes.read_text(encoding='utf-8'),
                      'packages': packages}, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > 2 * 1024 * 1024:
        parser.error('Update inventory exceeds the client size limit.')
    (args.assets / 'carkit-update.json').write_bytes(raw)
    (args.assets / 'carkit-update.json.sig').write_bytes(key.sign(raw))


if __name__ == '__main__':
    main()
