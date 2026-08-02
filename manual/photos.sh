#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# List (first 5)
curl -s "$BASE_URL/api/photos?_limit=5"

# Get by id
curl -s "$BASE_URL/api/photos/1"

# Filter by albumId
curl -s "$BASE_URL/api/photos?albumId=1"

# Search by title
curl -s "$BASE_URL/api/photos?q=accusamus"

# Paginate
curl -s "$BASE_URL/api/photos?_page=2&_limit=3"

# Sort by title desc
curl -s "$BASE_URL/api/photos?_sort=title&_order=desc"

# Create
curl -s -X POST "$BASE_URL/api/photos" \
  -H "Content-Type: application/json" \
  -d '{"albumId":1,"title":"new photo","url":"https://example.com/photo.jpg","thumbnailUrl":"https://example.com/thumb.jpg"}'

# Update (partial)
curl -s -X PATCH "$BASE_URL/api/photos/1" \
  -H "Content-Type: application/json" \
  -d '{"title":"updated photo title"}'

# Replace (full)
curl -s -X PUT "$BASE_URL/api/photos/1" \
  -H "Content-Type: application/json" \
  -d '{"albumId":1,"title":"accusamus beatae ad facilis cum similique qui sunt","url":"https://via.placeholder.com/600/92c952","thumbnailUrl":"https://via.placeholder.com/150/92c952"}'

# Delete
curl -s -X DELETE "$BASE_URL/api/photos/1"
