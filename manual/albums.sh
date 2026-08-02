#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# List (first 5)
curl -s "$BASE_URL/api/albums?_limit=5"

# Get by id
curl -s "$BASE_URL/api/albums/1"

# Filter by userId
curl -s "$BASE_URL/api/albums?userId=1"

# Search by title
curl -s "$BASE_URL/api/albums?q=quidem"

# Paginate
curl -s "$BASE_URL/api/albums?_page=1&_limit=3"

# Sort by title desc
curl -s "$BASE_URL/api/albums?_sort=title&_order=desc"

# Create
curl -s -X POST "$BASE_URL/api/albums" \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"new album"}'

# Update (partial)
curl -s -X PATCH "$BASE_URL/api/albums/1" \
  -H "Content-Type: application/json" \
  -d '{"title":"updated album title"}'

# Replace (full)
curl -s -X PUT "$BASE_URL/api/albums/1" \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"quidem molestiae enim"}'

# Delete the album we just created (no photos → safe to delete)
curl -s -X DELETE "$BASE_URL/api/albums/101"

# Nested: album's photos
curl -s "$BASE_URL/api/albums/1/photos"
