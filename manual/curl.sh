#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

curl "$BASE_URL/api/users" | jq length
curl "$BASE_URL/api/posts" | jq length
curl "$BASE_URL/api/comments" | jq length
curl "$BASE_URL/api/photos" | jq length
curl "$BASE_URL/api/todos" | jq length
