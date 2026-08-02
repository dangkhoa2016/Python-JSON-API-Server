#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# List (first 5)
curl -s "$BASE_URL/api/posts?_limit=5"

# Get by id
curl -s "$BASE_URL/api/posts/1"

# Filter by userId
curl -s "$BASE_URL/api/posts?userId=1"

# Search
curl -s "$BASE_URL/api/posts?q=qui"

# Paginate
curl -s "$BASE_URL/api/posts?_page=2&_limit=3"

# Sort by title desc
curl -s "$BASE_URL/api/posts?_sort=title&_order=desc"

# Create
curl -s -X POST "$BASE_URL/api/posts" \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"new post","body":"hello world"}'

# Update (partial)
curl -s -X PATCH "$BASE_URL/api/posts/1" \
  -H "Content-Type: application/json" \
  -d '{"title":"updated title"}'

# Replace (full)
curl -s -X PUT "$BASE_URL/api/posts/1" \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"title":"sunt aut facere repellat provident occaecati excepturi optio reprehenderit","body":"quia et suscipit\nsuscipit recusandae consequuntur expedita et cum\nreprehenderit molestiae ut ut quas totam\nnostrum rerum est autem sunt rem eveniet architecto"}'

# Delete the post we just created (safe — no dependent comments)
curl -s -X DELETE "$BASE_URL/api/posts/101"

# Nested: post's comments
curl -s "$BASE_URL/api/posts/1/comments"
