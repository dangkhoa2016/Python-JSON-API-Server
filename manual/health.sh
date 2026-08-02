#!/usr/bin/env bash
set -e

BASE_URL=http://localhost:3000

# Health check
curl -s "$BASE_URL/health" | jq .

# API root info
curl -s "$BASE_URL/api" | jq .

# CORS preflight
curl -s -X OPTIONS "$BASE_URL/api/todos" -I
