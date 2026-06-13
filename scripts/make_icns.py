#!/usr/bin/env python3
"""根据 PNG 生成 macOS 原生图标 (.icns 文件)"""

import struct, zlib, sys, os

def make_icns(png_path, icns_path):
    with open(png_path, 'rb') as f:
        png_data = f.read()

    PNGS = {
        16: 'icp4', 32: 'icp5', 48: 'ic07', 128: 'ic08', 256: 'ic09',
    }

    entries = []
    for size, ostype in PNGS.items():
        raw = zlib.compress(png_data, 9) if size < 256 else png_data
        header = ostype.encode() + struct.pack('>I', len(raw) + 8)
        entries.append(header + raw)

    body = b''.join(entries)
    icns = b'icns' + struct.pack('>I', len(body) + 8) + body
    with open(icns_path, 'wb') as f:
        f.write(icns)

if __name__ == '__main__':
    in_png = sys.argv[1]
    out_icns = sys.argv[2]
    make_icns(in_png, out_icns)
    print(f"Created: {out_icns}")
