"""
Debug specific nodes in ComfyUI metadata
"""
import struct
import json

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

def debug_nodes(path, node_ids):
    print(f"\n{'='*60}")
    print(f"DEBUG NODES: {path}")
    print('='*60)
    
    with open(path, 'rb') as f:
        data = f.read()
    
    chunks = read_png_chunks(data)
    prompt_data = None
    workflow_data = None
    
    for chunk_type, chunk_data, _ in chunks:
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1:
                keyword = chunk_data[:null_pos].decode('latin-1')
                value = chunk_data[null_pos+1:].decode('utf-8', errors='replace')
                try:
                    if keyword == 'prompt':
                        prompt_data = json.loads(value)
                    elif keyword == 'workflow':
                        workflow_data = json.loads(value)
                except:
                    pass
    
    print("\n=== PROMPT DATA (nodes) ===")
    if prompt_data:
        for node_id in node_ids:
            if node_id in prompt_data:
                print(f"\nNode {node_id}:")
                print(json.dumps(prompt_data[node_id], indent=2))
            else:
                print(f"\nNode {node_id}: NOT FOUND in prompt_data")
    
    print("\n=== WORKFLOW DATA (nodes with widgets_values) ===")
    if workflow_data:
        nodes = workflow_data.get('nodes', [])
        for node in nodes:
            node_id = str(node.get('id'))
            if node_id in node_ids:
                print(f"\nNode {node_id} (type: {node.get('type')}):")
                if 'widgets_values' in node:
                    print(f"  widgets_values: {json.dumps(node['widgets_values'], indent=2)}")
                else:
                    print("  (no widgets_values)")

if __name__ == '__main__':
    # Debug nodes for kotamota_00070
    debug_nodes('kotamota_00070.png', ['183', '188', '201'])
    
    print("\n" + "="*80 + "\n")
    
    # Debug nodes for Dross_00146
    debug_nodes('Dross_00146.png', ['183', '188'])
