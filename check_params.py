import struct

def read_png_chunks(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Not a valid PNG')
    chunks, pos = [], 8
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        chunk_type = data[pos+4:pos+8].decode('ascii')
        chunk_data = data[pos+8:pos+8+length]
        chunks.append((chunk_type, chunk_data))
        pos += 12 + length
        if chunk_type == 'IEND': break
    return chunks

with open('ComfyUI_14453_.png', 'rb') as f:
    data = f.read()

print("=== ALL CHUNKS IN ComfyUI_14453_.png ===")
for ct, cd in read_png_chunks(data):
    if ct == 'tEXt':
        np = cd.find(b'\x00')
        kw = cd[:np].decode('latin-1')
        print(f"  tEXt: '{kw}' ({len(cd)-np-1} bytes)")
    else:
        print(f"  {ct}: {len(cd)} bytes")
