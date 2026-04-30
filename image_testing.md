# Image Integration Testing Playbook

## Test Agent Rules for Image Integration
- Always use base64-encoded images (data URI format: `data:image/jpeg;base64,<payload>`)
- Formats: JPEG, PNG, WEBP only
- No SVG, BMP, HEIC, solid-color, or blank images
- Every image must have real visual features (objects, edges, text)
- For animated formats (GIF, APNG), extract first frame only
- Resize oversized images before upload

## For Cozii AI Receipt Scan
Endpoint: `POST /api/ai/scan-receipt`
Body: `{ "image_base64": "data:image/jpeg;base64,..." }`
Auth: Bearer token required

Expected response:
```json
{
  "items": [
    { "name": "Oat milk", "quantity": 1, "price": 4.99, "category_hint": "food" },
    { "name": "Toothpaste", "quantity": 2, "price": 6.50, "category_hint": "toiletries" }
  ]
}
```
