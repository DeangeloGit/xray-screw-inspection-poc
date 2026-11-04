"""Length-delimited messages for the private, local DINO worker."""
import json
import struct


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise EOFError('GPU 程序已結束')
        data.extend(part)
    return bytes(data)


def receive(stream):
    size = struct.unpack('<I', read_exact(stream, 4))[0]
    if not 0 < size <= 65536:
        raise ValueError('無效 GPU 訊息')
    header = json.loads(read_exact(stream, size))
    length = header.get('bytes', 0)
    if type(length) is not int or not 0 <= length <= 16 * 1024 * 1024:
        raise ValueError('無效 GPU 資料長度')
    return header, read_exact(stream, length)


def send(stream, header, payload=b''):
    header = json.dumps(dict(header, bytes=len(payload)), ensure_ascii=False).encode('utf-8')
    stream.write(struct.pack('<I', len(header)) + header + payload)
    stream.flush()
