"""
Convert ComfyUI metadata to A1111 format
"""
import struct
import zlib
import json
import sys
import os

def read_png_chunks(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("Not a valid PNG file")
    chunks, pos = [], 8
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        chunk_type = data[pos+4:pos+8].decode('ascii')
        chunk_data = data[pos+8:pos+8+length]
        crc = struct.unpack('>I', data[pos+8+length:pos+12+length])[0]
        chunks.append((chunk_type, chunk_data, crc))
        pos += 12 + length
        if chunk_type == 'IEND': break
    return chunks

def make_chunk(chunk_type, data):
    chunk_type_bytes = chunk_type.encode('ascii')
    crc = zlib.crc32(chunk_type_bytes + data) & 0xffffffff
    return struct.pack('>I', len(data)) + chunk_type_bytes + data + struct.pack('>I', crc)

def extract_comfy_prompts(png_path):
    """Extract positive and negative prompts from ComfyUI metadata"""
    with open(png_path, 'rb') as f:
        data = f.read()
    
    chunks = read_png_chunks(data)
    prompt_data = None
    
    for chunk_type, chunk_data, _ in chunks:
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1:
                keyword = chunk_data[:null_pos].decode('latin-1')
                if keyword == 'prompt':
                    value = chunk_data[null_pos+1:].decode('utf-8', errors='replace')
                    prompt_data = json.loads(value)
                    break
    
    if not prompt_data:
        return None, None
    
    positive = ""
    negative = ""
    
    # Search for text-containing nodes
    for node_id, node_data in prompt_data.items():
        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})
        meta = node_data.get('_meta', {})
        title = meta.get('title', '').lower()
        
        # Various text encoding nodes
        if class_type in ('CLIPTextEncode', 'CLIPTextEncodeSDXL', 'TextEncodeEditAdvanced', 
                          'FluxGuidance', 'ConditioningConcat'):
            # Check for 'text' or 'prompt' field
            text = inputs.get('text') or inputs.get('prompt', '')
            
            if text:
                # Determine if positive or negative
                if 'negative' in title or 'neg' in title:
                    negative = text
                elif not positive:  # First text is usually positive
                    positive = text
    
    return positive, negative

def convert_comfy_to_a1111(png_path, output_path=None, backup=True):
    """Convert ComfyUI PNG to A1111 format"""
    positive, negative = extract_comfy_prompts(png_path)
    
    if not positive:
        print(f"No ComfyUI prompts found in {png_path}")
        return False
    
    # Build A1111-style metadata
    metadata = positive
    if negative:
        metadata += f"\nNegative prompt: {negative}"
    
    # Add placeholder parameters (since ComfyUI doesn't store them the same way)
    metadata += "\nSteps: 20, Sampler: Euler, CFG scale: 7, Seed: -1, Size: 512x512"
    
    # Read original PNG
    with open(png_path, 'rb') as f:
        data = f.read()
    
    chunks = read_png_chunks(data)
    
    # Build new PNG with A1111 parameters
    new_data = b'\x89PNG\r\n\x1a\n'
    written = False
    
    for chunk_type, chunk_data, _ in chunks:
        # Skip ComfyUI chunks
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1:
                keyword = chunk_data[:null_pos].decode('latin-1')
                if keyword in ('prompt', 'workflow'):
                    continue
        
        # Insert A1111 parameters before IDAT
        if chunk_type == 'IDAT' and not written:
            new_data += make_chunk('tEXt', b'parameters\x00' + metadata.encode('latin-1', errors='replace'))
            written = True
        
        new_data += make_chunk(chunk_type, chunk_data)
    
    # Backup
    if backup:
        backup_path = png_path + '.comfy_backup'
        if not os.path.exists(backup_path):
            import shutil
            shutil.copy2(png_path, backup_path)
    
    # Write
    output = output_path or png_path
    with open(output, 'wb') as f:
        f.write(new_data)
    
    print(f"Converted: {png_path}")
    print(f"Positive: {positive[:100]}...")
    if negative:
        print(f"Negative: {negative[:100]}...")
    
    return True

def batch_convert(folder):
    """Convert all ComfyUI PNGs in folder"""
    converted = 0
    for f in os.listdir(folder):
        if f.lower().endswith('.png'):
            path = os.path.join(folder, f)
            try:
                if convert_comfy_to_a1111(path):
                    converted += 1
            except Exception as e:
                print(f"Error converting {f}: {e}")
    print(f"\nConverted {converted} files")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python comfy_converter.py <image.png>        # Convert single file")
        print("  python comfy_converter.py <folder>           # Convert all PNGs in folder")
        sys.exit(1)
    
    path = sys.argv[1]
    
    if os.path.isdir(path):
        batch_convert(path)
    elif os.path.isfile(path):
        convert_comfy_to_a1111(path)
    else:
        print(f"Path not found: {path}")
        sys.exit(1)
