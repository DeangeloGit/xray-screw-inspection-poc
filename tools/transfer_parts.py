"""Split an encrypted XRAYENC1 file and reassemble it without a key."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata

MAGIC = b'XRAYENC1'
BLOCK = 1024 * 1024


def safe_name(value):
    if (not isinstance(value, str) or not value or value in ('.', '..')
            or any(c in value for c in '/\\<>:"|?*')
            or any(ord(c) < 32 for c in value) or value.endswith((' ', '.'))
            or value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}):
        raise ValueError('Unsafe file name')
    return value


def digest_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Invalid SHA-256')
    return value


def split_file(source, directory, chunk_bytes):
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if type(chunk_bytes) is not int or chunk_bytes <= 0:
        raise ValueError('Part size must be positive')
    safe_name(source.name)
    with source.open('rb') as stream:
        if stream.read(len(MAGIC)) != MAGIC:
            raise ValueError('Only XRAYENC1 encrypted files can be split')
        stream.seek(0)
        directory.mkdir(parents=True, exist_ok=False)
        whole, total, parts = hashlib.sha256(), 0, []
        while True:
            first = stream.read(min(BLOCK, chunk_bytes))
            if not first:
                break
            name = source.name + '.part' + str(len(parts) + 1).zfill(3)
            part_hash, size = hashlib.sha256(), 0
            with (directory / name).open('xb') as part:
                block = first
                while block:
                    part.write(block)
                    part_hash.update(block)
                    whole.update(block)
                    size += len(block)
                    total += len(block)
                    if size == chunk_bytes:
                        break
                    block = stream.read(min(BLOCK, chunk_bytes - size))
            parts.append(dict(filename=name, bytes=size, sha256=part_hash.hexdigest()))
    manifest = dict(schema_version=1, format='XRAYENC1-parts',
                    original_filename=source.name, total_bytes=total,
                    sha256=whole.hexdigest(), parts=parts)
    path = directory / (source.name + '.parts.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return dict(ok=True, manifest=str(path), parts=len(parts), bytes=total, sha256=manifest['sha256'])


def validate_manifest(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ValueError('Unsupported manifest schema')
    if value.get('format') != 'XRAYENC1-parts':
        raise ValueError('Unsupported parts format')
    safe_name(value.get('original_filename'))
    digest_value(value.get('sha256'))
    if type(value.get('total_bytes')) is not int or value['total_bytes'] < len(MAGIC):
        raise ValueError('Invalid encrypted file size')
    parts = value.get('parts')
    if not isinstance(parts, list) or not parts:
        raise ValueError('Parts list must not be empty')
    seen, total = set(), 0
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError('Invalid part record')
        name = safe_name(part.get('filename'))
        key = unicodedata.normalize('NFC', name).casefold()
        if key in seen:
            raise ValueError('Duplicate part file name')
        seen.add(key)
        if type(part.get('bytes')) is not int or part['bytes'] <= 0:
            raise ValueError('Invalid part size')
        digest_value(part.get('sha256'))
        total += part['bytes']
    if total != value['total_bytes']:
        raise ValueError('Part sizes do not equal total size')
    return value


def publish_no_clobber(temporary, destination):
    # Same-directory hard-link publication is atomic and refuses an existing
    # name on both Windows and POSIX, unlike POSIX rename which can overwrite.
    os.link(temporary, destination)
    Path(temporary).unlink()


def join_file(manifest_path, output):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    with manifest_path.open(encoding='utf-8-sig') as stream:
        manifest = validate_manifest(json.load(stream))
    sidecar = Path(str(output) + '.sha256')
    if output.exists() or sidecar.exists():
        raise ValueError('Output or checksum already exists; choose a new file')
    paths = []
    for part in manifest['parts']:
        path = manifest_path.parent / part['filename']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != part['bytes']:
            raise ValueError('Missing, linked or incorrectly sized part: ' + part['filename'])
        paths.append(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=output.name + '.', suffix='.partial', dir=output.parent)
    temporary = Path(temporary_name)
    checksum_temp = None
    try:
        whole, total, header = hashlib.sha256(), 0, b''
        with os.fdopen(descriptor, 'wb') as target:
            for path, expected in zip(paths, manifest['parts']):
                part_hash, size = hashlib.sha256(), 0
                with path.open('rb') as source:
                    for block in iter(lambda: source.read(BLOCK), b''):
                        if len(header) < len(MAGIC):
                            header += block[:len(MAGIC) - len(header)]
                        target.write(block)
                        part_hash.update(block)
                        whole.update(block)
                        size += len(block)
                        total += len(block)
                if size != expected['bytes'] or part_hash.hexdigest() != expected['sha256']:
                    raise ValueError('Part checksum mismatch: ' + path.name)
        if header != MAGIC:
            raise ValueError('Reassembled file is not XRAYENC1')
        if total != manifest['total_bytes'] or whole.hexdigest() != manifest['sha256']:
            raise ValueError('Whole encrypted file checksum mismatch')
        descriptor, name = tempfile.mkstemp(prefix=sidecar.name + '.', suffix='.partial', dir=output.parent)
        checksum_temp = Path(name)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(whole.hexdigest() + '  ' + output.name + '\n')
        if output.exists() or sidecar.exists():
            raise ValueError('Output or checksum appeared during reassembly')
        publish_no_clobber(temporary, output)
        publish_no_clobber(checksum_temp, sidecar)
        return dict(ok=True, output=str(output), parts=len(paths), bytes=total,
                    sha256=whole.hexdigest(), checksum=str(sidecar))
    finally:
        temporary.unlink(missing_ok=True)
        if checksum_temp is not None:
            checksum_temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    split = commands.add_parser('split')
    split.add_argument('encrypted', type=Path)
    split.add_argument('--output-dir', required=True, type=Path)
    split.add_argument('--part-mib', type=float, default=256)
    join = commands.add_parser('join')
    join.add_argument('manifest', type=Path)
    join.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'split':
            if not math.isfinite(args.part_mib) or args.part_mib <= 0:
                raise ValueError('Part MiB must be finite and positive')
            result = split_file(args.encrypted, args.output_dir, int(args.part_mib * 1024 * 1024))
        else:
            result = join_file(args.manifest, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, OverflowError) as exc:
        print(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
