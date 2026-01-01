# Technical Documentation

## Architecture

The application is a single-file Flask web server with an embedded HTML/CSS/JS frontend.

```
metadata_editor.py
├── PNG Functions (read/write chunks)
├── JPG Functions (read/write EXIF)
├── HTML Template (inline)
│   ├── CSS (design system)
│   └── JavaScript (UI logic)
└── Flask Routes (REST API)
```

## PNG Metadata Format

### tEXt Chunk

Simple text chunk used by older A1111 versions.

```
Chunk structure:
┌─────────────┬──────────────┬───────────┬─────────┐
│ Length (4B) │ Type "tEXt"  │ Data      │ CRC (4B)│
└─────────────┴──────────────┴───────────┴─────────┘

Data format:
┌────────────────┬──────┬─────────────────┐
│ Keyword        │ NULL │ Text            │
│ "parameters"   │ \x00 │ prompt data...  │
└────────────────┴──────┴─────────────────┘
```

Encoding: Latin-1 (ISO-8859-1)

### iTXt Chunk

International text chunk with UTF-8 support.

```
Data format:
┌─────────┬──────┬─────────────┬────────────┬──────┬────────────┬──────┬──────┐
│ Keyword │ NULL │ Compression │ Comp.      │ Lang │ Translated │ NULL │ Text │
│         │      │ Flag (1B)   │ Method(1B) │ \x00 │ Keyword    │      │      │
└─────────┴──────┴─────────────┴────────────┴──────┴────────────┴──────┴──────┘
```

- Compression Flag: 0 = uncompressed, 1 = zlib compressed
- Encoding: UTF-8

## JPG Metadata Format

A1111 stores metadata in EXIF UserComment field as UTF-16BE encoded text.

```
JPEG structure:
┌────────┬─────────────────┬─────────────────┬────────────┐
│ SOI    │ APP1 (EXIF)     │ Other segments  │ Image data │
│ FFD8   │ FFE1 + data     │ ...             │ FFDB...    │
└────────┴─────────────────┴─────────────────┴────────────┘
```

The metadata is located between the EXIF header and the DQT marker (FFD8).

## Backup System

When saving with backup enabled:

1. Check if `{filename}.backup` exists
2. If not, copy original to `{filename}.backup`
3. Write new metadata to original file

Backups are never overwritten, preserving the original state.

## UI Design System

### CSS Variables

```css
--bg-base: #F8FAFC;      /* Page background */
--bg-surface: #FFFFFF;    /* Card background */
--accent: #3B82F6;        /* Primary actions */
--success: #10B981;       /* Success states */
--error: #EF4444;         /* Error states */
```

### Spacing

8px grid system. All spacing values are multiples of 8px.

### Typography

- UI: Inter (system fallback: -apple-system, Segoe UI)
- Code: JetBrains Mono (monospace fallback)

## State Management

Client-side state tracking:

```javascript
imageStates = {
  "path/to/image.png": {
    hasBackup: true,      // Server-side backup exists
    modified: false,      // Local unsaved changes
    original: "..."       // Original metadata for comparison
  }
}
```

Status transitions:
- `pristine` → `modified` (on edit)
- `modified` → `saved` (on save)
- `pristine` → `saved` (on save)

## Security Considerations

⚠️ This application is designed for local use only.

- No authentication
- File system access based on user input
- Should not be exposed to public networks

For production deployment, consider:
- Adding authentication
- Restricting accessible paths
- Running behind a reverse proxy
