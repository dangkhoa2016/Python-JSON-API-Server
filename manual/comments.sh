#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# List (first 5)
curl -s "$BASE_URL/api/comments?_limit=5"

# Get by id
curl -s "$BASE_URL/api/comments/1"

# Filter by postId
curl -s "$BASE_URL/api/comments?postId=1"

# Search by email
curl -s "$BASE_URL/api/comments?q=Lew"

# Paginate
curl -s "$BASE_URL/api/comments?_page=1&_limit=3"

# Sort by name desc
curl -s "$BASE_URL/api/comments?_sort=name&_order=desc"

# Create
curl -s -X POST "$BASE_URL/api/comments" \
  -H "Content-Type: application/json" \
  -d '{"postId":1,"name":"test comment","email":"test@example.com","body":"nice post!"}'

# Update (partial)
curl -s -X PATCH "$BASE_URL/api/comments/1" \
  -H "Content-Type: application/json" \
  -d '{"body":"updated body"}'

# Replace (full)
curl -s -X PUT "$BASE_URL/api/comments/1" \
  -H "Content-Type: application/json" \
  -d '{"postId":1,"name":"id labore ex et quam laborum","email":"Eliseo@gardner.biz","body":"laudantium enim quasi est quidem magnam voluptate ipsam eos\ntempora quo necessitatibus\ndolor quam autem quasi\nreiciendis et nam sapiente accusantium"}'

# Delete
curl -s -X DELETE "$BASE_URL/api/comments/1"
