"""
Analyze PNG metadata to debug ComfyUI conversion issues
"""
import struct
import json
import sys

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

def analyze_image(path):
    print(f"\n{'='*60}")
    print(f"ANALYZING: {path}")
    print('='*60)
    
    with open(path, 'rb') as f:
        data = f.read()
    
    chunks = read_png_chunks(data)
    
    text_chunks = []
    for chunk_type, chunk_data, _ in chunks:
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1:
                keyword = chunk_data[:null_pos].decode('latin-1')
                value = chunk_data[null_pos+1:].decode('utf-8', errors='replace')
                text_chunks.append((keyword, value))
    
    print(f"\nFound {len(text_chunks)} text chunks:")
    for keyword, value in text_chunks:
        print(f"\n--- Keyword: {keyword} ---")
        print(f"Length: {len(value)} chars")
        print(f"Preview: {value[:500]}...")
        
        # Try to parse as JSON
        try:
            parsed = json.loads(value)
            print(f"\n[Valid JSON] Keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'list/other'}")
            
            if isinstance(parsed, dict):
                # For prompt data, show class_types
                class_types = set()
                for node_id, node_data in parsed.items():
                    if isinstance(node_data, dict) and 'class_type' in node_data:
                        class_types.add(node_data['class_type'])
                if class_types:
                    print(f"Class types found: {sorted(class_types)}")
                    
                    # Look for text-related nodes
                    for node_id, node_data in parsed.items():
                        class_type = node_data.get('class_type', '')
                        inputs = node_data.get('inputs', {})
                        meta = node_data.get('_meta', {})
                        
                        if 'text' in inputs or 'prompt' in inputs:
                            print(f"\n  Node {node_id} ({class_type}):")
                            print(f"    Meta: {meta}")
                            text = inputs.get('text') or inputs.get('prompt')
                            if isinstance(text, str) and len(text) > 10:
                                print(f"    Text: {text[:200]}...")
                            elif isinstance(text, list):
                                print(f"    Text ref: {text}")
        except json.JSONDecodeError:
            print("[Not valid JSON]")
            # Check if it looks like A1111 parameters
            if 'Steps:' in value and 'Sampler:' in value:
                print("[Looks like A1111 parameters]")

if __name__ == '__main__':
    files = [
        'Dross_00009.png',
        'Dross_00146.png', 
        'kotamota_00070.png'
    ]
    
    for f in files:
        try:
            analyze_image(f)
        except Exception as e:
            print(f"Error analyzing {f}: {e}")
