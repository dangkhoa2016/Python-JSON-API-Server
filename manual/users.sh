#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# List (first 5)
curl -s "$BASE_URL/api/users?_limit=5"

# Get by id
curl -s "$BASE_URL/api/users/1"

# Filter by username
curl -s "$BASE_URL/api/users?username=Bret"

# Search
curl -s "$BASE_URL/api/users?q=Leanne"

# Paginate
curl -s "$BASE_URL/api/users?_page=1&_limit=3"

# Sort by name desc
curl -s "$BASE_URL/api/users?_sort=name&_order=desc"

# Create
curl -s -X POST "$BASE_URL/api/users" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","username":"testuser","email":"test@example.com"}'

# Update (partial)
curl -s -X PATCH "$BASE_URL/api/users/1" \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com"}'

# Replace (full)
curl -s -X PUT "$BASE_URL/api/users/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"Leanne Graham","username":"Bret","email":"Sincere@april.biz","phone":"1-770-736-8031 x56442","website":"hildegard.org"}'

# Delete
curl -s -X DELETE "$BASE_URL/api/users/1"

# Nested: user's posts
curl -s "$BASE_URL/api/users/1/posts"

# Nested: user's albums
curl -s "$BASE_URL/api/users/1/albums"

# Nested: user's todos
curl -s "$BASE_URL/api/users/1/todos"
