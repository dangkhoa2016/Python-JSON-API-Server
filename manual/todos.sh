#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# List (first 5)
curl -s "$BASE_URL/api/todos?_limit=5"

# Get by id
curl -s "$BASE_URL/api/todos/1"

# Filter by userId + completed
curl -s "$BASE_URL/api/todos?userId=1&completed=true"

# Search by title
curl -s "$BASE_URL/api/todos?q=delectus"

# Paginate: page 2, limit 3
curl -s "$BASE_URL/api/todos?_page=2&_limit=3"

# Sort by title desc
curl -s "$BASE_URL/api/todos?_sort=title&_order=desc"

# Create
curl -s -X POST "$BASE_URL/api/todos" \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"learn curl","completed":false}'

# Update (partial)
curl -s -X PATCH "$BASE_URL/api/todos/1" \
  -H "Content-Type: application/json" \
  -d '{"completed":true}'

# Replace (full)
curl -s -X PUT "$BASE_URL/api/todos/1" \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"delectus aut autem","completed":false}'

# Delete the todo we just created
curl -s -X DELETE "$BASE_URL/api/todos/201"
