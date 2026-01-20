"""
A1111 Metadata Editor - Professional Web UI
Clean, modern light theme with resizable panels
"""
import os
import struct
import zlib
import shutil
import json
from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

# ============== PNG Functions ==============
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

# ============== ComfyUI Converter ==============
def is_comfyui_png(png_path):
    """Check if PNG has ComfyUI metadata"""
    try:
        with open(png_path, 'rb') as f:
            data = f.read()
        for chunk_type, chunk_data, _ in read_png_chunks(data):
            if chunk_type == 'tEXt':
                null_pos = chunk_data.find(b'\x00')
                if null_pos != -1:
                    keyword = chunk_data[:null_pos].decode('latin-1')
                    if keyword in ('prompt', 'workflow'):
                        return True
        return False
    except:
        return False

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

def convert_comfy_to_a1111(png_path, create_backup=True):
    """Add A1111-style parameters to ComfyUI PNG while preserving workflow"""
    positive, negative = extract_comfy_prompts(png_path)
    params = extract_comfy_params(png_path)
    
    if not positive:
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
    if create_backup:
        backup_path = png_path + '.comfy_backup'
        if not os.path.exists(backup_path):
            shutil.copy2(png_path, backup_path)
    
    # Write
    with open(png_path, 'wb') as f:
        f.write(new_data)
    
    return True

def extract_png_metadata(png_path):
    """Extract metadata from PNG, auto-converting ComfyUI if needed"""
    # First try to read A1111 metadata
    with open(png_path, 'rb') as f:
        data = f.read()
    
    for chunk_type, chunk_data, _ in read_png_chunks(data):
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1 and chunk_data[:null_pos].decode('latin-1') == 'parameters':
                return chunk_data[null_pos+1:].decode('latin-1')
        elif chunk_type == 'iTXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1 and chunk_data[:null_pos].decode('latin-1') == 'parameters':
                rest = chunk_data[null_pos+1:]
                compression_flag = rest[0]
                text_start = 2
                for _ in range(2):
                    next_null = rest.find(b'\x00', text_start)
                    if next_null != -1:
                        text_start = next_null + 1
                text_data = rest[text_start:]
                if compression_flag == 0:
                    return text_data.decode('utf-8')
                else:
                    return zlib.decompress(text_data).decode('utf-8')
    
    # If no A1111 metadata found, check if it's ComfyUI and convert
    if is_comfyui_png(png_path):
        if convert_comfy_to_a1111(png_path, create_backup=True):
            # Read again after conversion
            return extract_png_metadata(png_path)
    
    return ""

def write_png_metadata(png_path, metadata_text, create_backup=True):
    with open(png_path, 'rb') as f:
        data = f.read()
    chunks = read_png_chunks(data)
    new_data = b'\x89PNG\r\n\x1a\n'
    written = False
    for chunk_type, chunk_data, _ in chunks:
        # Handle both tEXt and iTXt chunks with 'parameters' keyword
        if chunk_type in ('tEXt', 'iTXt'):
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1 and chunk_data[:null_pos].decode('latin-1') == 'parameters':
                # Write as tEXt (simpler, works with A1111)
                new_data += make_chunk('tEXt', b'parameters\x00' + metadata_text.encode('latin-1', errors='replace'))
                written = True
                continue
        if chunk_type == 'IDAT' and not written:
            new_data += make_chunk('tEXt', b'parameters\x00' + metadata_text.encode('latin-1', errors='replace'))
            written = True
        new_data += make_chunk(chunk_type, chunk_data)
    if create_backup:
        backup = png_path + '.backup'
        if not os.path.exists(backup): shutil.copy2(png_path, backup)
    with open(png_path, 'wb') as f:
        f.write(new_data)

# ============== JPG Functions ==============
def extract_jpg_metadata(jpg_path):
    with open(jpg_path, 'rb') as f:
        data = f.read()
    try:
        start, end = data.find(b'\x00<'), data.find(b'\xff\xdb')
        if start == -1 or end == -1: return ""
        return data[start:end].decode('utf-16be')
    except: return ""

def write_jpg_metadata(jpg_path, metadata_text, create_backup=True):
    with open(jpg_path, 'rb') as f:
        data = f.read()
    start, end = data.find(b'\x00<'), data.find(b'\xff\xdb')
    if start == -1 or end == -1:
        raise ValueError("Cannot find metadata section")
    new_data = data[:start] + metadata_text.encode('utf-16be') + data[end:]
    if create_backup:
        backup = jpg_path + '.backup'
        if not os.path.exists(backup): shutil.copy2(jpg_path, backup)
    with open(jpg_path, 'wb') as f:
        f.write(new_data)

# ============== HTML Template ==============
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Metadata Editor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
    --bg-base: #F8FAFC;
    --bg-surface: #FFFFFF;
    --bg-elevated: #FFFFFF;
    --bg-subtle: #F1F5F9;
    --border-default: #E2E8F0;
    --border-muted: #F1F5F9;
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-muted: #94A3B8;
    --accent: #3B82F6;
    --accent-hover: #2563EB;
    --accent-subtle: #EFF6FF;
    --success: #10B981;
    --success-subtle: #ECFDF5;
    --error: #EF4444;
    --error-subtle: #FEF2F2;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04);
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --transition: 150ms ease;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 14px; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg-base);
    color: var(--text-primary);
    line-height: 1.5;
    height: 100vh;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
}

/* Layout */
.app { display: flex; height: 100vh; }

/* Sidebar */
.sidebar {
    width: 320px;
    min-width: 240px;
    max-width: 480px;
    background: var(--bg-surface);
    border-right: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    position: relative;
}
.sidebar-header {
    padding: 20px;
    border-bottom: 1px solid var(--border-default);
}
.logo {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 20px;
}
.logo-icon {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, var(--accent), #8B5CF6);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 18px;
}
.logo-text {
    font-weight: 600;
    font-size: 16px;
    color: var(--text-primary);
}
.logo-text span { color: var(--text-muted); font-weight: 400; font-size: 12px; display: block; margin-top: 2px; }

.input-group { position: relative; }
.input-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
}
.folder-input {
    width: 100%;
    padding: 10px 12px 10px 38px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    font-size: 13px;
    color: var(--text-primary);
    background: var(--bg-surface);
    transition: var(--transition);
    outline: none;
}
.folder-input:hover { border-color: var(--text-muted); }
.folder-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-subtle); }
.folder-input::placeholder { color: var(--text-muted); }

.load-btn {
    width: 100%;
    margin-top: 12px;
    padding: 10px 16px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
}
.load-btn:hover { background: var(--accent-hover); }
.load-btn:active { transform: scale(0.98); }

/* Image List */
.list-header {
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-muted);
}
.list-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.list-count { font-size: 12px; color: var(--text-muted); background: var(--bg-subtle); padding: 2px 8px; border-radius: 10px; }

.image-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}
.image-list::-webkit-scrollbar { width: 6px; }
.image-list::-webkit-scrollbar-track { background: transparent; }
.image-list::-webkit-scrollbar-thumb { background: var(--border-default); border-radius: 3px; }
.image-list::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

.image-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: var(--transition);
    border: 2px solid transparent;
    margin-bottom: 2px;
}
.image-item:hover { background: var(--bg-subtle); }
.image-item.active {
    background: var(--accent-subtle);
    border-color: var(--accent);
}
.image-item.active .item-name { color: var(--accent); font-weight: 500; }

.item-thumb {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-sm);
    object-fit: cover;
    background: var(--bg-subtle);
    flex-shrink: 0;
    position: relative;
}
.thumb-wrapper {
    position: relative;
    flex-shrink: 0;
}
.status-badge {
    position: absolute;
    bottom: -2px;
    right: -2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    border: 2px solid var(--bg-surface);
    z-index: 1;
}
.status-badge.pristine { background: var(--bg-subtle); color: var(--text-muted); }
.status-badge.modified { background: #FEF3C7; color: #D97706; }
.status-badge.saved { background: var(--success-subtle); color: var(--success); }
.status-badge.comfy { background: #DBEAFE; color: #2563EB; }
.item-info { flex: 1; min-width: 0; }
.item-name {
    font-size: 13px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.item-type {
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-top: 2px;
}

/* Resize Handle */
.resize-handle {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    cursor: col-resize;
    background: transparent;
    transition: background var(--transition);
    z-index: 10;
}
.resize-handle:hover, .resize-handle.active { background: var(--accent); }

/* Main Content */
.main {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 20px;
    gap: 16px;
    min-width: 0;
    background: var(--bg-base);
}

.panels {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
}

/* Panel Base */
.panel {
    background: var(--bg-surface);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
}
.panel-header {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--bg-subtle);
}
.panel-icon { font-size: 16px; }
.panel-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); }

/* Preview Panel */
.preview-panel { flex: 1; min-width: 280px; }
.preview-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: 
        linear-gradient(45deg, var(--bg-subtle) 25%, transparent 25%),
        linear-gradient(-45deg, var(--bg-subtle) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, var(--bg-subtle) 75%),
        linear-gradient(-45deg, transparent 75%, var(--bg-subtle) 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
    overflow: hidden;
}
.preview-content img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg);
}
.empty-state {
    text-align: center;
    color: var(--text-muted);
}
.empty-state-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.5; }
.empty-state-text { font-size: 14px; }

/* Panel Resizer */
.panel-resizer {
    width: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: col-resize;
    flex-shrink: 0;
}
.panel-resizer-bar {
    width: 4px;
    height: 48px;
    background: var(--border-default);
    border-radius: 2px;
    transition: var(--transition);
}
.panel-resizer:hover .panel-resizer-bar,
.panel-resizer.active .panel-resizer-bar {
    background: var(--accent);
    height: 64px;
}

/* Metadata Panel */
.metadata-panel { flex: 1; min-width: 320px; }
.metadata-content { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.metadata-textarea {
    flex: 1;
    padding: 16px 18px;
    border: none;
    background: transparent;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    resize: none;
    outline: none;
}
.metadata-textarea::placeholder { color: var(--text-muted); }

/* Controls */
.controls {
    padding: 14px 18px;
    border-top: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--bg-subtle);
    flex-wrap: wrap;
}
.btn {
    padding: 10px 20px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    gap: 8px;
}
.btn:hover { background: var(--accent-hover); }
.btn:active { transform: scale(0.98); }
.btn-secondary {
    background: var(--bg-surface);
    color: var(--text-secondary);
    border: 1px solid var(--border-default);
}
.btn-secondary:hover { background: var(--bg-subtle); border-color: var(--text-muted); }

.checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
    cursor: pointer;
    margin-left: auto;
    user-select: none;
}
.checkbox-input {
    width: 16px;
    height: 16px;
    accent-color: var(--accent);
    cursor: pointer;
}

/* Batch Replace Modal */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    visibility: hidden;
    transition: all 0.2s;
}
.modal-overlay.show { opacity: 1; visibility: visible; }
.modal {
    background: var(--bg-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    width: 100%;
    max-width: 480px;
    transform: scale(0.95);
    transition: transform 0.2s;
}
.modal-overlay.show .modal { transform: scale(1); }
.modal-header {
    padding: 18px 20px;
    border-bottom: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.modal-title { font-size: 16px; font-weight: 600; }
.modal-close {
    width: 32px;
    height: 32px;
    border: none;
    background: transparent;
    cursor: pointer;
    border-radius: var(--radius-sm);
    font-size: 18px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    justify-content: center;
}
.modal-close:hover { background: var(--bg-subtle); color: var(--text-primary); }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 16px; }
.form-label { display: block; font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px; }
.form-input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    font-size: 13px;
    outline: none;
    transition: var(--transition);
}
.form-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-subtle); }
.modal-footer {
    padding: 16px 20px;
    border-top: 1px solid var(--border-default);
    display: flex;
    justify-content: flex-end;
    gap: 12px;
}

/* Toast */
.toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(calc(100% + 24px));
    padding: 12px 20px;
    background: var(--bg-elevated);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg);
    border: 1px solid var(--border-default);
    font-size: 13px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    z-index: 1000;
}
.toast.show { transform: translateX(-50%) translateY(0); }
.toast.success { border-color: var(--success); }
.toast.success .toast-icon { color: var(--success); }
.toast.error { border-color: var(--error); }
.toast.error .toast-icon { color: var(--error); }
.toast-icon { font-size: 16px; }

/* Responsive */
@media (max-width: 1024px) {
    .panels { flex-direction: column; }
    .panel-resizer { width: 100%; height: 12px; cursor: row-resize; }
    .panel-resizer-bar { width: 48px; height: 4px; }
    .preview-panel, .metadata-panel { min-width: 0; min-height: 200px; }
}
@media (max-width: 768px) {
    .sidebar { position: fixed; left: 0; top: 0; bottom: 0; z-index: 100; transform: translateX(-100%); transition: transform 0.3s ease; }
    .sidebar.open { transform: translateX(0); box-shadow: var(--shadow-lg); }
    .main { padding: 12px; }
}
</style>
</head>
<body>
<div class="app">
    <aside class="sidebar" id="sidebar">
        <header class="sidebar-header">
            <div class="logo">
                <div class="logo-icon">✦</div>
                <div class="logo-text">Metadata Editor<span>A1111 WebUI</span></div>
            </div>
            <div class="input-group">
                <span class="input-icon">📁</span>
                <input type="text" class="folder-input" id="folderPath" placeholder="Путь к папке...">
            </div>
            <button class="load-btn" onclick="loadFolder()">
                <span>↻</span> Загрузить изображения
            </button>
        </header>
        <div class="list-header">
            <span class="list-title">Изображения</span>
            <span class="list-count" id="imageCount">0</span>
        </div>
        <div class="image-list" id="imageList"></div>
        <div class="resize-handle" id="sidebarHandle"></div>
    </aside>

    <main class="main">
        <div class="panels">
            <section class="panel preview-panel" id="previewPanel">
                <header class="panel-header">
                    <span class="panel-icon">🖼</span>
                    <span class="panel-title">Превью</span>
                </header>
                <div class="preview-content" id="preview">
                    <div class="empty-state">
                        <div class="empty-state-icon">📷</div>
                        <div class="empty-state-text">Выберите изображение</div>
                    </div>
                </div>
            </section>

            <div class="panel-resizer" id="panelResizer">
                <div class="panel-resizer-bar"></div>
            </div>

            <section class="panel metadata-panel" id="metadataPanel">
                <header class="panel-header">
                    <span class="panel-icon">📝</span>
                    <span class="panel-title">Метаданные</span>
                </header>
                <div class="metadata-content">
                    <textarea class="metadata-textarea" id="metadata" placeholder="Выберите изображение для просмотра метаданных..."></textarea>
                </div>
                <div class="controls">
                    <button class="btn" onclick="saveMetadata()">
                        <span>💾</span> Сохранить
                    </button>
                    <button class="btn btn-secondary" onclick="openBatchModal()">
                        <span>🔄</span> Пакетная замена
                    </button>
                    <button class="btn btn-secondary" onclick="convertAllComfy()" id="convertComfyBtn" style="display:none;">
                        <span>⚡</span> Исправить Comfy
                    </button>
                    <label class="checkbox-label">
                        <input type="checkbox" class="checkbox-input" id="createBackup" checked>
                        Создавать бэкап
                    </label>
                </div>
            </section>
        </div>
    </main>
</div>

<!-- Batch Replace Modal -->
<div class="modal-overlay" id="batchModal">
    <div class="modal">
        <div class="modal-header">
            <span class="modal-title">🔄 Пакетная замена</span>
            <button class="modal-close" onclick="closeBatchModal()">×</button>
        </div>
        <div class="modal-body">
            <div class="form-group">
                <label class="form-label">Найти текст</label>
                <input type="text" class="form-input" id="findText" placeholder="например: girl">
            </div>
            <div class="form-group">
                <label class="form-label">Заменить на</label>
                <input type="text" class="form-input" id="replaceText" placeholder="например: woman">
            </div>
            <div class="form-group">
                <label class="checkbox-label" style="margin-left: 0;">
                    <input type="checkbox" class="checkbox-input" id="batchBackup" checked>
                    Создавать бэкапы
                </label>
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" onclick="closeBatchModal()">Отмена</button>
            <button class="btn" onclick="executeBatchReplace()">Заменить во всех</button>
        </div>
    </div>
</div>

<div class="toast" id="toast">
    <span class="toast-icon"></span>
    <span class="toast-text"></span>
</div>

<script>
let currentImage = null;
let currentFolder = '';
let originalMetadata = '';
let imageStates = {}; // path -> {original, current, saved}

// Sidebar resize
const sidebar = document.getElementById('sidebar');
const sidebarHandle = document.getElementById('sidebarHandle');
let resizingSidebar = false;

sidebarHandle.onmousedown = () => {
    resizingSidebar = true;
    sidebarHandle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
};

// Panel resize
const previewPanel = document.getElementById('previewPanel');
const panelResizer = document.getElementById('panelResizer');
let resizingPanels = false;

panelResizer.onmousedown = () => {
    resizingPanels = true;
    panelResizer.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
};

document.onmousemove = (e) => {
    if (resizingSidebar) {
        const w = Math.min(480, Math.max(240, e.clientX));
        sidebar.style.width = w + 'px';
    }
    if (resizingPanels) {
        const panels = document.querySelector('.panels');
        const rect = panels.getBoundingClientRect();
        const offset = e.clientX - rect.left;
        const pw = Math.min(rect.width - 332, Math.max(280, offset));
        previewPanel.style.flex = 'none';
        previewPanel.style.width = pw + 'px';
    }
};

document.onmouseup = () => {
    resizingSidebar = false;
    resizingPanels = false;
    sidebarHandle.classList.remove('active');
    panelResizer.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
};

async function loadFolder() {
    const path = document.getElementById('folderPath').value;
    if (!path) return showToast('Введите путь к папке', 'error');
    
    const res = await fetch('/api/list?path=' + encodeURIComponent(path));
    const data = await res.json();
    if (data.error) return showToast(data.error, 'error');
    
    currentFolder = data.folder;
    imageStates = {};
    
    const list = document.getElementById('imageList');
    list.innerHTML = '';
    data.images.forEach(img => {
        const ext = img.name.split('.').pop().toUpperCase();
        const div = document.createElement('div');
        div.className = 'image-item';
        div.dataset.path = img.path;
        
        // Status: pristine, saved, comfy
        let status, statusIcon, statusTitle;
        if (img.is_comfy) {
            status = 'comfy';
            statusIcon = '🔄';
            statusTitle = 'ComfyUI (будет конвертирован)';
        } else if (img.has_backup) {
            status = 'saved';
            statusIcon = '✓';
            statusTitle = 'Редактировался';
        } else {
            status = 'pristine';
            statusIcon = '○';
            statusTitle = 'Оригинал';
        }
        
        imageStates[img.path] = { hasBackup: img.has_backup, modified: false, isComfy: img.is_comfy };
        
        div.innerHTML = `
            <div class="thumb-wrapper">
                <img class="item-thumb" src="/api/thumb?path=${encodeURIComponent(img.path)}" loading="lazy">
                <span class="status-badge ${status}" title="${statusTitle}">${statusIcon}</span>
            </div>
            <div class="item-info">
                <div class="item-name">${img.name}</div>
                <div class="item-type">${ext}</div>
            </div>`;
        div.onclick = () => selectImage(img.path, div);
        list.appendChild(div);
    });
    document.getElementById('imageCount').textContent = data.images.length;
    
    let msg = `Загружено ${data.images.length} изображений`;
    if (data.comfy_count > 0) {
        msg += ` (${data.comfy_count} ComfyUI)`;
        document.getElementById('convertComfyBtn').style.display = 'flex';
    } else {
        document.getElementById('convertComfyBtn').style.display = 'none';
    }
    showToast(msg, 'success');
}

async function selectImage(path, el) {
    // Check if current has unsaved changes
    if (currentImage && imageStates[currentImage]?.modified) {
        updateItemStatus(currentImage, 'modified');
    }
    
    document.querySelectorAll('.image-item').forEach(e => e.classList.remove('active'));
    el.classList.add('active');
    currentImage = path;
    document.getElementById('preview').innerHTML = `<img src="/api/image?path=${encodeURIComponent(path)}">`;
    
    // Show loading for ComfyUI files
    if (imageStates[path]?.isComfy) {
        showToast('Конвертация ComfyUI → A1111...', 'success');
    }
    
    const res = await fetch('/api/metadata?path=' + encodeURIComponent(path));
    const data = await res.json();
    const metadata = data.metadata || '';
    document.getElementById('metadata').value = metadata;
    originalMetadata = metadata;
    
    if (imageStates[path]) {
        imageStates[path].original = metadata;
        // After conversion, update status
        if (imageStates[path].isComfy && metadata) {
            imageStates[path].isComfy = false;
            imageStates[path].hasBackup = true;
            updateItemStatus(path, 'saved');
            showToast('ComfyUI конвертирован в A1111', 'success');
        }
    }
}

// Track changes in textarea
document.getElementById('metadata').addEventListener('input', () => {
    if (!currentImage) return;
    const current = document.getElementById('metadata').value;
    const isModified = current !== originalMetadata;
    if (imageStates[currentImage]) {
        imageStates[currentImage].modified = isModified;
    }
    updateItemStatus(currentImage, isModified ? 'modified' : (imageStates[currentImage]?.hasBackup ? 'saved' : 'pristine'));
});

function updateItemStatus(path, status) {
    const item = document.querySelector(`.image-item[data-path="${CSS.escape(path)}"]`);
    if (!item) return;
    const badge = item.querySelector('.status-badge');
    if (!badge) return;
    
    badge.className = 'status-badge ' + status;
    if (status === 'pristine') {
        badge.textContent = '○';
        badge.title = 'Оригинал';
    } else if (status === 'saved') {
        badge.textContent = '✓';
        badge.title = 'Сохранён';
    } else if (status === 'modified') {
        badge.textContent = '●';
        badge.title = 'Не сохранён';
    } else if (status === 'comfy') {
        badge.textContent = '🔄';
        badge.title = 'ComfyUI';
    }
}

async function saveMetadata() {
    if (!currentImage) return showToast('Сначала выберите изображение', 'error');
    const res = await fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            path: currentImage,
            metadata: document.getElementById('metadata').value,
            backup: document.getElementById('createBackup').checked
        })
    });
    const data = await res.json();
    if (data.error) {
        showToast(data.error, 'error');
    } else {
        showToast('Сохранено!', 'success');
        originalMetadata = document.getElementById('metadata').value;
        if (imageStates[currentImage]) {
            imageStates[currentImage].modified = false;
            imageStates[currentImage].hasBackup = true;
        }
        updateItemStatus(currentImage, 'saved');
    }
}

// Batch replace modal
function openBatchModal() {
    if (!currentFolder) return showToast('Сначала загрузите папку', 'error');
    document.getElementById('batchModal').classList.add('show');
    document.getElementById('findText').focus();
}

function closeBatchModal() {
    document.getElementById('batchModal').classList.remove('show');
    document.getElementById('findText').value = '';
    document.getElementById('replaceText').value = '';
}

async function executeBatchReplace() {
    const find = document.getElementById('findText').value;
    const replace = document.getElementById('replaceText').value;
    const backup = document.getElementById('batchBackup').checked;
    
    if (!find) return showToast('Введите текст для поиска', 'error');
    
    const res = await fetch('/api/batch-replace', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ folder: currentFolder, find, replace, backup })
    });
    const data = await res.json();
    
    if (data.error) {
        showToast(data.error, 'error');
    } else {
        closeBatchModal();
        showToast(`Изменено ${data.modified} файлов`, 'success');
        // Reload to update statuses
        loadFolder();
    }
}

async function convertAllComfy() {
    if (!currentFolder) return showToast('Сначала загрузите папку', 'error');
    
    showToast('Конвертация ComfyUI файлов...', 'success');
    
    const res = await fetch('/api/convert-comfy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ folder: currentFolder })
    });
    const data = await res.json();
    
    if (data.error) {
        showToast(data.error, 'error');
    } else {
        let msg = `Конвертировано ${data.converted} файлов`;
        if (data.errors && data.errors.length > 0) {
            msg += ` (${data.errors.length} ошибок)`;
            console.log('Conversion errors:', data.errors);
        }
        showToast(msg, 'success');
        // Reload to update statuses
        loadFolder();
    }
}

// Close modal on overlay click
document.getElementById('batchModal').onclick = (e) => {
    if (e.target.id === 'batchModal') closeBatchModal();
};

// Close modal on Escape
document.onkeydown = (e) => {
    if (e.key === 'Escape') closeBatchModal();
};

function showToast(msg, type) {
    const toast = document.getElementById('toast');
    toast.querySelector('.toast-icon').textContent = type === 'success' ? '✓' : '✕';
    toast.querySelector('.toast-text').textContent = msg;
    toast.className = 'toast ' + type + ' show';
    setTimeout(() => toast.classList.remove('show'), 3000);
}

document.getElementById('folderPath').onkeypress = (e) => { if (e.key === 'Enter') loadFolder(); };
document.getElementById('findText').onkeypress = (e) => { if (e.key === 'Enter') executeBatchReplace(); };
</script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/list')
def list_images():
    folder = request.args.get('path', '')
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': 'Папка не найдена'})
    images = []
    converted_count = 0
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
            full_path = os.path.join(folder, f)
            has_backup = os.path.exists(full_path + '.backup')
            is_comfy = False
            
            # Check if it's a ComfyUI file
            if f.lower().endswith('.png'):
                is_comfy = is_comfyui_png(full_path)
                if is_comfy:
                    converted_count += 1
            
            images.append({
                'name': f, 
                'path': full_path, 
                'has_backup': has_backup,
                'is_comfy': is_comfy
            })
    return jsonify({
        'images': images, 
        'folder': folder,
        'comfy_count': converted_count
    })

@app.route('/api/thumb')
def get_thumb():
    path = request.args.get('path', '')
    return send_file(path) if os.path.exists(path) else ('', 404)

@app.route('/api/image')
def get_image():
    path = request.args.get('path', '')
    return send_file(path) if os.path.exists(path) else ('', 404)

@app.route('/api/metadata')
def get_metadata():
    path = request.args.get('path', '')
    if not os.path.exists(path):
        return jsonify({'error': 'Файл не найден'})
    try:
        ext = path.lower().split('.')[-1]
        metadata = extract_png_metadata(path) if ext == 'png' else extract_jpg_metadata(path)
        return jsonify({'metadata': metadata})
    except Exception as e:
        return jsonify({'metadata': '', 'error': str(e)})

@app.route('/api/save', methods=['POST'])
def save_metadata():
    data = request.json
    path, metadata, backup = data.get('path', ''), data.get('metadata', ''), data.get('backup', True)
    if not os.path.exists(path):
        return jsonify({'error': 'Файл не найден'})
    try:
        ext = path.lower().split('.')[-1]
        (write_png_metadata if ext == 'png' else write_jpg_metadata)(path, metadata, backup)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/batch-replace', methods=['POST'])
def batch_replace():
    data = request.json
    folder = data.get('folder', '')
    find_text = data.get('find', '')
    replace_text = data.get('replace', '')
    backup = data.get('backup', True)
    
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': 'Папка не найдена'})
    if not find_text:
        return jsonify({'error': 'Укажите текст для поиска'})
    
    modified = 0
    errors = []
    
    for f in os.listdir(folder):
        if not f.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        path = os.path.join(folder, f)
        try:
            ext = f.lower().split('.')[-1]
            metadata = extract_png_metadata(path) if ext == 'png' else extract_jpg_metadata(path)
            if find_text in metadata:
                new_metadata = metadata.replace(find_text, replace_text)
                (write_png_metadata if ext == 'png' else write_jpg_metadata)(path, new_metadata, backup)
                modified += 1
        except Exception as e:
            errors.append(f'{f}: {str(e)}')
    
    return jsonify({'modified': modified, 'errors': errors})

@app.route('/api/check-status')
def check_status():
    path = request.args.get('path', '')
    if not os.path.exists(path):
        return jsonify({'status': 'unknown'})
    backup_path = path + '.backup'
    has_backup = os.path.exists(backup_path)
    return jsonify({'has_backup': has_backup})

@app.route('/api/convert-comfy', methods=['POST'])
def convert_comfy_batch():
    """Convert all ComfyUI files in folder to A1111 format"""
    data = request.json
    folder = data.get('folder', '')
    
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': 'Папка не найдена'})
    
    converted = 0
    errors = []
    
    for f in os.listdir(folder):
        if not f.lower().endswith('.png'):
            continue
        path = os.path.join(folder, f)
        try:
            if is_comfyui_png(path):
                if convert_comfy_to_a1111(path, create_backup=True):
                    converted += 1
        except Exception as e:
            errors.append(f'{f}: {str(e)}')
    
    return jsonify({'converted': converted, 'errors': errors})

if __name__ == '__main__':
    print("=" * 50)
    print("  Metadata Editor")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
