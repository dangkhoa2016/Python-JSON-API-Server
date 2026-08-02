#!/usr/bin/env bash
set -e
DB="${1:-storage/data.db}"
DIR=$(dirname "$0")

sqlite3 -header -column "$DB" <<SQL
$(awk '
  /^--  [0-9]+\./ {
    gsub(/^--  /, "")
    title = $0
    line = title; gsub(/./, "─", line)
    print ".print \"\""
    print ".print \"┌─" line "─┐\""
    print ".print \"│ " title " │\""
    print ".print \"└─" line "─┘\""
    next
  }
  /^-- =/        { next }
  /^--  Usage/   { next }
  /^--  \.\.\./  { next }
  /^--$/         { next }
  1
' "$DIR/inspect-queries.sql")
SQL
