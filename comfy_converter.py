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
    
    if not prompt_data:
        return None, None
    
    # Build a map of workflow node widgets_values by node ID
    workflow_widgets = {}
    if workflow_data:
        for node in workflow_data.get('nodes', []):
            node_id = str(node.get('id', ''))
            if node_id and 'widgets_values' in node:
                workflow_widgets[node_id] = node.get('widgets_values', [])
    
    def resolve_input(value, visited=None):
        """Resolve node references to actual values, following reference chains"""
        if visited is None:
            visited = set()
        
        if isinstance(value, list) and len(value) == 2:
            # Reference to another node [node_id, output_index]
            ref_node_id = str(value[0])
            
            # Prevent infinite loops
            if ref_node_id in visited:
                return ""
            visited.add(ref_node_id)
            
            if ref_node_id in prompt_data:
                ref_node = prompt_data[ref_node_id]
                ref_class = ref_node.get('class_type', '')
                ref_inputs = ref_node.get('inputs', {})
                
                # ShowText|pysssss nodes store text in text_0 or widgets
                if 'ShowText' in ref_class or 'PrimitiveNode' in ref_class or 'String' in ref_class:
                    # Check inputs first
                    for key in ['text', 'text_0', 'string', 'value']:
                        if key in ref_inputs:
                            val = ref_inputs[key]
                            if isinstance(val, str) and len(val) > 10:
                                return val
                            # Also check if it's a reference
                            resolved = resolve_input(val, visited)
                            if resolved:
                                return resolved
                    
                    # Check workflow widgets_values
                    if ref_node_id in workflow_widgets:
                        widgets = workflow_widgets[ref_node_id]
                        for item in widgets:
                            if isinstance(item, str) and len(item) > 50:
                                return item
                            elif isinstance(item, list):
                                for subitem in item:
                                    if isinstance(subitem, str) and len(subitem) > 50:
                                        return subitem
                
                # Simple Load Line From Text File - try external file FIRST, then workflow widgets
                if 'Load Line From Text File' in ref_class or 'LoadLineFromTextFile' in ref_class:
                    # FIRST: Try to read from external file if specified
                    file_path = ref_inputs.get('file_path', '')
                    
                    # Use 'count' as start line if it seems valid (ComfyUI stores actual index there in random mode)
                    # Otherwise use 'start'
                    start_line = ref_inputs.get('count', 0)
                    if not start_line:
                        start_line = ref_inputs.get('start', 0)
                        
                    prefix = ref_inputs.get('prefix', '')
                    postfix = ref_inputs.get('postfix', '')
                    
                    if file_path and os.path.exists(file_path):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as ext_file:
                                lines = ext_file.readlines()
                                if start_line > 0 and start_line <= len(lines):
                                    line_text = lines[start_line - 1].strip()
                                    if line_text:
                                        parts = []
                                        if prefix:
                                            parts.append(prefix)
                                        parts.append(line_text)
                                        if postfix:
                                            parts.append(postfix)
                                        return ' '.join(parts)
                        except Exception:
                            pass
                    
                    # SECOND: Fall back to workflow widgets_values (static template text)
                    if ref_node_id in workflow_widgets:
                        widgets = workflow_widgets[ref_node_id]
                        # Look for long text strings in widgets_values
                        for item in widgets:
                            if isinstance(item, str) and len(item) > 50:
                                return item
                            elif isinstance(item, list):
                                for subitem in item:
                                    if isinstance(subitem, str) and len(subitem) > 50:
                                        return subitem
                    
                    # THIRD: Combine prefix/postfix as fallback
                    parts = []
                    if 'prefix' in ref_inputs and ref_inputs['prefix']:
                        parts.append(str(ref_inputs['prefix']))
                    if 'postfix' in ref_inputs and ref_inputs['postfix']:
                        parts.append(str(ref_inputs['postfix']))
                    if parts:
                        return ' '.join(parts)
                
                # Try to get text from referenced node inputs
                for key in ['text', 'text_0', 'prompt', 'STRING', 'text_g', 'text_l']:
                    if key in ref_inputs:
                        val = resolve_input(ref_inputs[key], visited)
                        if val and len(val) > 10:
                            return val
                
        return value if isinstance(value, str) else ""
    
    positive = ""
    negative = ""
    prefix = ""
    postfix = ""
    
    # Search for text-containing nodes in prompt data
    for node_id, node_data in prompt_data.items():
        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})
        meta = node_data.get('_meta', {})
        title = meta.get('title', '').lower()
        
        # Text file loader nodes - extract prefix/postfix
        if 'Load Line From Text File' in class_type or 'LoadLineFromTextFile' in class_type:
            if 'prefix' in inputs and inputs['prefix']:
                prefix = inputs['prefix']
            if 'postfix' in inputs and inputs['postfix']:
                postfix = inputs['postfix']
        
        # ShowText nodes - check for text_0 directly
        if 'ShowText' in class_type:
            if 'text_0' in inputs:
                text_0 = inputs['text_0']
                if isinstance(text_0, str) and len(text_0) > 50:
                    if not positive or len(text_0) > len(positive):
                        positive = text_0
        
        # Various text encoding nodes
        if class_type in ('CLIPTextEncode', 'CLIPTextEncodeSDXL', 'TextEncodeEditAdvanced', 
                          'FluxGuidance', 'ConditioningConcat'):
            text_raw = inputs.get('text') or inputs.get('prompt', '')
            text = resolve_input(text_raw)
            
            if text and len(text) > 50:  # Only count as found if substantial text
                if 'negative' in title or 'neg' in title:
                    if not negative or len(text) > len(negative):
                        negative = text
                elif 'positive' in title or not positive:
                    if not positive or len(text) > len(positive):
                        positive = text
    
    # If no substantial prompt text found, check workflow widgets_values
    if not positive or len(positive) < 50:
        if workflow_data:
            nodes = workflow_data.get('nodes', [])
            for node in nodes:
                node_type = node.get('type', '')
                widgets_values = node.get('widgets_values', [])
                
                # Skip certain node types that won't have prompts
                if node_type in ('KSamplerSelect', 'VAELoader', 'UNETLoader'):
                    continue
                
                if widgets_values:
                    for item in widgets_values:
                        if isinstance(item, str) and len(item) > 50:
                            # Prefer text from ShowText nodes
                            if 'ShowText' in node_type or not positive:
                                positive = item
                                if 'ShowText' in node_type:
                                    break  # Found it in ShowText, stop
                        elif isinstance(item, list):
                            for subitem in item:
                                if isinstance(subitem, str) and len(subitem) > 50:
                                    if 'ShowText' in node_type or not positive:
                                        positive = subitem
                                        break
                            if positive and len(positive) > 50 and 'ShowText' in node_type:
                                break
                if positive and len(positive) > 50:
                    # Continue looking in case there's a ShowText node
                    pass
    
    # Combine prefix + positive + postfix (avoid duplicates)
    if positive:
        parts = []
        if prefix and prefix not in positive:
            parts.append(prefix)
        parts.append(positive)
        if postfix and postfix not in positive:
            parts.append(postfix)
        positive = ' '.join(parts).strip()
    elif prefix or postfix:
        # Fallback: if no positive text found but we have prefix/postfix, use them
        parts = []
        if prefix:
            parts.append(prefix)
        if postfix:
            parts.append(postfix)
        positive = ' '.join(parts).strip()
        if positive:
            positive += " [Prompt text was stored in external file]"
    
    return positive, negative

def extract_comfy_params(png_path):
    """Extract generation parameters from ComfyUI metadata"""
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
                    try:
                        prompt_data = json.loads(value)
                    except:
                        pass
                    break
    
    if not prompt_data:
        return {}
    
    params = {
        'seed': -1,
        'steps': 20,
        'cfg': 7.0,
        'sampler': 'euler',
        'scheduler': 'normal',
        'width': 512,
        'height': 512,
        'denoise': 1.0
    }
    
    # Search for parameters in nodes
    for node_id, node_data in prompt_data.items():
        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})
        
        # KSampler nodes
        if class_type in ('KSampler', 'KSamplerAdvanced'):
            if 'seed' in inputs and isinstance(inputs['seed'], (int, float)):
                params['seed'] = int(inputs['seed'])
            if 'steps' in inputs and isinstance(inputs['steps'], (int, float)):
                params['steps'] = int(inputs['steps'])
            if 'cfg' in inputs and isinstance(inputs['cfg'], (int, float)):
                params['cfg'] = float(inputs['cfg'])
            if 'sampler_name' in inputs and isinstance(inputs['sampler_name'], str):
                params['sampler'] = inputs['sampler_name']
            if 'scheduler' in inputs and isinstance(inputs['scheduler'], str):
                params['scheduler'] = inputs['scheduler']
            if 'denoise' in inputs and isinstance(inputs['denoise'], (int, float)):
                params['denoise'] = float(inputs['denoise'])
        
        # KSamplerSelect node
        if class_type == 'KSamplerSelect':
            if 'sampler_name' in inputs and isinstance(inputs['sampler_name'], str):
                params['sampler'] = inputs['sampler_name']
        
        # RandomNoise node (for Flux workflows)
        if class_type == 'RandomNoise':
            if 'noise_seed' in inputs and isinstance(inputs['noise_seed'], (int, float)):
                params['seed'] = int(inputs['noise_seed'])
        
        # Scheduler nodes (Flux2Scheduler, etc.)
        if 'Scheduler' in class_type:
            if 'steps' in inputs and isinstance(inputs['steps'], (int, float)):
                params['steps'] = int(inputs['steps'])
        
        # Latent/Size nodes - handle both direct values and references
        if class_type in ('EmptyLatentImage', 'EmptyFlux2LatentImage', 'EmptySD3LatentImage'):
            width_val = inputs.get('width')
            height_val = inputs.get('height')
            
            # Direct values
            if isinstance(width_val, (int, float)):
                params['width'] = int(width_val)
            elif isinstance(width_val, list) and len(width_val) == 2:
                # Reference to PrimitiveInt node
                ref_id = str(width_val[0])
                if ref_id in prompt_data:
                    ref_node = prompt_data[ref_id]
                    if ref_node.get('class_type') == 'PrimitiveInt':
                        ref_inputs = ref_node.get('inputs', {})
                        if 'value' in ref_inputs and isinstance(ref_inputs['value'], (int, float)):
                            params['width'] = int(ref_inputs['value'])
            
            if isinstance(height_val, (int, float)):
                params['height'] = int(height_val)
            elif isinstance(height_val, list) and len(height_val) == 2:
                # Reference to PrimitiveInt node
                ref_id = str(height_val[0])
                if ref_id in prompt_data:
                    ref_node = prompt_data[ref_id]
                    if ref_node.get('class_type') == 'PrimitiveInt':
                        ref_inputs = ref_node.get('inputs', {})
                        if 'value' in ref_inputs and isinstance(ref_inputs['value'], (int, float)):
                            params['height'] = int(ref_inputs['value'])
        
        # PrimitiveInt nodes might have width/height in their meta title
        if class_type == 'PrimitiveInt':
            meta = node_data.get('_meta', {})
            title = meta.get('title', '').lower()
            value = inputs.get('value')
            if isinstance(value, (int, float)):
                if 'width' in title:
                    params['width'] = int(value)
                elif 'height' in title:
                    params['height'] = int(value)
        
        # FluxGuidance for cfg
        if class_type == 'FluxGuidance':
            if 'guidance' in inputs and isinstance(inputs['guidance'], (int, float)):
                params['cfg'] = float(inputs['guidance'])
    
    return params

def convert_comfy_to_a1111(png_path, output_path=None, backup=True):
    """Add A1111-style parameters to ComfyUI PNG while preserving workflow"""
    positive, negative = extract_comfy_prompts(png_path)
    params = extract_comfy_params(png_path)
    
    if not positive:
        print(f"No ComfyUI prompts found in {png_path}")
        return False
    
    # Build A1111-style metadata string
    metadata = positive
    if negative:
        metadata += f"\nNegative prompt: {negative}"
    
    # Build parameters line
    param_parts = [
        f"Steps: {params.get('steps', 20)}",
        f"Sampler: {params.get('sampler', 'euler')}",
        f"Scheduler: {params.get('scheduler', 'normal')}",
        f"CFG scale: {params.get('cfg', 7.0)}",
        f"Seed: {params.get('seed', -1)}",
        f"Size: {params.get('width', 512)}x{params.get('height', 512)}",
    ]
    if params.get('denoise', 1.0) < 1.0:
        param_parts.append(f"Denoising strength: {params.get('denoise')}")
    param_parts.append("Tool: ComfyUI")
    
    metadata += "\n" + ", ".join(param_parts)
    
    # Read original PNG
    with open(png_path, 'rb') as f:
        data = f.read()
    
    chunks = read_png_chunks(data)
    
    # Build new PNG - KEEP prompt and workflow chunks, ADD parameters
    new_data = b'\x89PNG\r\n\x1a\n'
    has_parameters = False
    
    for chunk_type, chunk_data, _ in chunks:
        # Check if parameters already exists
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1:
                keyword = chunk_data[:null_pos].decode('latin-1')
                if keyword == 'parameters':
                    # Replace existing parameters chunk
                    new_data += make_chunk('tEXt', b'parameters\x00' + metadata.encode('utf-8', errors='replace'))
                    has_parameters = True
                    continue
        
        # Insert parameters before first IDAT if not yet added
        if chunk_type == 'IDAT' and not has_parameters:
            new_data += make_chunk('tEXt', b'parameters\x00' + metadata.encode('utf-8', errors='replace'))
            has_parameters = True
        
        # Keep all original chunks (including prompt and workflow)
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
    print(f"Params: Seed={params.get('seed')}, Steps={params.get('steps')}, CFG={params.get('cfg')}")
    
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
