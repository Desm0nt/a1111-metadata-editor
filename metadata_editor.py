"""
A1111 Metadata Editor - Professional Web UI
Clean, modern light theme with resizable panels
"""
import os
import struct
import zlib
import shutil
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

def extract_png_metadata(png_path):
    with open(png_path, 'rb') as f:
        data = f.read()
    for chunk_type, chunk_data, _ in read_png_chunks(data):
        if chunk_type == 'tEXt':
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1 and chunk_data[:null_pos].decode('latin-1') == 'parameters':
                return chunk_data[null_pos+1:].decode('latin-1')
        elif chunk_type == 'iTXt':
            # iTXt format: keyword\x00compression_flag\x00compression_method\x00language\x00translated_keyword\x00text
            null_pos = chunk_data.find(b'\x00')
            if null_pos != -1 and chunk_data[:null_pos].decode('latin-1') == 'parameters':
                # Skip: keyword\x00 + compression_flag(1) + compression_method(1) + language\x00 + translated\x00
                rest = chunk_data[null_pos+1:]
                # compression_flag and compression_method are single bytes
                compression_flag = rest[0]
                # Skip compression_flag, compression_method, then find two more nulls (language, translated_keyword)
                text_start = 2  # skip compression bytes
                for _ in range(2):  # skip language and translated_keyword
                    next_null = rest.find(b'\x00', text_start)
                    if next_null != -1:
                        text_start = next_null + 1
                text_data = rest[text_start:]
                if compression_flag == 0:
                    return text_data.decode('utf-8')
                else:
                    import zlib
                    return zlib.decompress(text_data).decode('utf-8')
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
        
        // Status: pristine (нетронутый), saved (сохранён/есть бэкап), modified (изменён, не сохранён)
        const status = img.has_backup ? 'saved' : 'pristine';
        const statusIcon = img.has_backup ? '✓' : '○';
        const statusTitle = img.has_backup ? 'Редактировался' : 'Оригинал';
        
        imageStates[img.path] = { hasBackup: img.has_backup, modified: false };
        
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
    showToast(`Загружено ${data.images.length} изображений`, 'success');
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
    const res = await fetch('/api/metadata?path=' + encodeURIComponent(path));
    const data = await res.json();
    const metadata = data.metadata || '';
    document.getElementById('metadata').value = metadata;
    originalMetadata = metadata;
    
    if (imageStates[path]) {
        imageStates[path].original = metadata;
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
        // Reload current image metadata if it was modified
        if (currentImage) {
            const metaRes = await fetch('/api/metadata?path=' + encodeURIComponent(currentImage));
            const metaData = await metaRes.json();
            document.getElementById('metadata').value = metaData.metadata || '';
            originalMetadata = metaData.metadata || '';
        }
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
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
            full_path = os.path.join(folder, f)
            has_backup = os.path.exists(full_path + '.backup')
            images.append({'name': f, 'path': full_path, 'has_backup': has_backup})
    return jsonify({'images': images, 'folder': folder})

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

if __name__ == '__main__':
    print("=" * 50)
    print("  Metadata Editor")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
