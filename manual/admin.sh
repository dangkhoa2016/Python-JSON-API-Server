#!/usr/bin/env bash
set -e

ADMIN_KEY=your-secret-admin-key
BASE_URL=http://localhost:3000

# List all settings (admin only)
curl -s "$BASE_URL/api/admin/settings" \
  -H "Authorization: Bearer $ADMIN_KEY"

# Update a setting
curl -s -X PATCH "$BASE_URL/api/admin/settings/DEFAULT_PAGE_SIZE" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"value":20}'

# Reset database (delete all data, re-seed from JSONPlaceholder)
curl -s -X POST "$BASE_URL/api/admin/reset-database" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
