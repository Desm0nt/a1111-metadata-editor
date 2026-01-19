# ComfyUI Converter

Convert ComfyUI workflow metadata to Automatic1111 format.

## Why?

ComfyUI stores metadata as JSON workflow data in `prompt` and `workflow` chunks. This format is not compatible with:
- Automatic1111 WebUI
- Most image viewers
- Civitai (for metadata display)

This converter extracts the text prompts and converts them to A1111's simple text format.

## Usage

### Single File

```bash
python comfy_converter.py image.png
```

Creates a backup as `image.png.comfy_backup` and converts the file in-place.

### Batch Convert Folder

```bash
python comfy_converter.py /path/to/folder
```

Converts all PNG files in the folder.

## What Gets Converted

### Extracted from ComfyUI:
- Positive prompt (from text encoding nodes)
- Negative prompt (if present)

### Added as Placeholders:
- Steps: 20
- Sampler: Euler
- CFG scale: 7
- Seed: -1
- Size: 512x512

> Note: ComfyUI doesn't store generation parameters in the same way as A1111, so these are placeholder values. Edit them manually after conversion if needed.

## Supported Node Types

The converter recognizes these ComfyUI node types:
- `CLIPTextEncode`
- `CLIPTextEncodeSDXL`
- `TextEncodeEditAdvanced` (Flux)
- `FluxGuidance`
- `ConditioningConcat`

## After Conversion

After converting, you can:
1. Open the file in the Metadata Editor web UI
2. Edit the placeholder parameters
3. Use batch replace to clean up prompts for Civitai

## Example

**Before (ComfyUI):**
```json
{
  "147": {
    "inputs": {
      "prompt": "a beautiful landscape, mountains, sunset",
      ...
    },
    "class_type": "TextEncodeEditAdvanced"
  }
}
```

**After (A1111):**
```
a beautiful landscape, mountains, sunset
Steps: 20, Sampler: Euler, CFG scale: 7, Seed: -1, Size: 512x512
```
