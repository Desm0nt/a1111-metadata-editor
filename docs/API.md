# API Reference

The application exposes a REST API for all operations.

## Endpoints

### GET /

Returns the main HTML page.

---

### GET /api/list

List all images in a folder.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| path | string | Absolute path to folder |

**Response:**
```json
{
  "images": [
    {
      "name": "00001.png",
      "path": "C:/images/00001.png",
      "has_backup": false
    }
  ],
  "folder": "C:/images"
}
```

**Errors:**
```json
{"error": "Папка не найдена"}
```

---

### GET /api/thumb

Get image thumbnail.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| path | string | Absolute path to image |

**Response:** Image file (binary)

---

### GET /api/image

Get full-size image.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| path | string | Absolute path to image |

**Response:** Image file (binary)

---

### GET /api/metadata

Extract metadata from image.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| path | string | Absolute path to image |

**Response:**
```json
{
  "metadata": "prompt text here\nNegative prompt: ...\nSteps: 20, ..."
}
```

---

### POST /api/save

Save metadata to image.

**Request Body:**
```json
{
  "path": "C:/images/00001.png",
  "metadata": "new prompt text",
  "backup": true
}
```

**Response:**
```json
{"success": true}
```

**Errors:**
```json
{"error": "Файл не найден"}
```

---

### POST /api/batch-replace

Find and replace text in all images in a folder.

**Request Body:**
```json
{
  "folder": "C:/images",
  "find": "girl",
  "replace": "woman",
  "backup": true
}
```

**Response:**
```json
{
  "modified": 5,
  "errors": []
}
```

---

### GET /api/check-status

Check if image has a backup file.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| path | string | Absolute path to image |

**Response:**
```json
{"has_backup": true}
```
