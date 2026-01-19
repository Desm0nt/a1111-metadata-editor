# Changelog

## [1.1.0] - 2025-01-19

### Added
- **ComfyUI Auto-Conversion**: Automatically detects and converts ComfyUI workflow metadata to A1111 format
- ComfyUI files are marked with 🔄 icon in the file list
- Conversion happens automatically when you click on a ComfyUI image
- Original ComfyUI data is backed up as `.comfy_backup`
- Status indicator shows conversion progress
- Batch replace functionality for quick text replacements across all images
- Real-time status tracking (pristine, modified, saved, ComfyUI)

### Changed
- Improved metadata extraction to support both `tEXt` and `iTXt` PNG chunks
- Enhanced UI with better status indicators
- Added support for Flux and other ComfyUI node types

### Fixed
- Better error handling for corrupted metadata
- Improved UTF-8 encoding support

## [1.0.0] - 2025-01-19

### Initial Release
- Web-based metadata editor for A1111 images
- Support for PNG (tEXt/iTXt) and JPG (EXIF) formats
- Visual browser with thumbnails
- Resizable panels
- Backup system
- Modern light theme UI
