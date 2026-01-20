"""Analyze problematic files"""
import struct
import json

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

def analyze(path):
    print(f"\n{'='*60}")
    print(f"FILE: {path}")
    print('='*60)
    
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print("FILE NOT FOUND!")
        return
    
    for ct, cd in read_png_chunks(data):
        if ct == 'tEXt':
            np = cd.find(b'\x00')
            kw = cd[:np].decode('latin-1')
            val = cd[np+1:].decode('utf-8', errors='replace')
            print(f"\ntEXt '{kw}' ({len(val)} chars)")
            
            if kw == 'parameters':
                print(f"  Content: {val[:300]}...")
            elif kw == 'prompt':
                try:
                    parsed = json.loads(val)
                    print(f"  Valid JSON with {len(parsed)} nodes")
                    # Show class types
                    types = set()
                    for nid, nd in parsed.items():
                        ct = nd.get('class_type', '')
                        if ct:
                            types.add(ct)
                    print(f"  Class types: {sorted(types)[:10]}...")
                except:
                    print(f"  NOT VALID JSON: {val[:200]}...")
            elif kw == 'workflow':
                print("  (workflow data)")
            else:
                print(f"  Content: {val[:200]}...")
        elif ct == 'iTXt':
            np = cd.find(b'\x00')
            kw = cd[:np].decode('latin-1')
            print(f"\niTXt '{kw}' ({len(cd)} bytes)")
        elif ct not in ('IDAT', 'IEND', 'IHDR'):
            print(f"\n{ct}: {len(cd)} bytes")

# Test files
files = ['kotamota_00002_.png', 'kotamota_00004.png']
for f in files:
    analyze(f)
