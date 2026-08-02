-- ==============================================================================
--  Database Inspection — python-json-api-server
--  Usage:  sqlite3 storage/data.db < manual/inspect-queries.sql
-- ==============================================================================

--  1. OVERVIEW
--  ..............................................................................
SELECT 'users'    AS table_name, COUNT(*) AS row_count FROM users
UNION ALL SELECT 'posts',    COUNT(*) FROM posts
UNION ALL SELECT 'comments', COUNT(*) FROM comments
UNION ALL SELECT 'albums',   COUNT(*) FROM albums
UNION ALL SELECT 'photos',   COUNT(*) FROM photos
UNION ALL SELECT 'todos',    COUNT(*) FROM todos
ORDER BY row_count DESC;

SELECT m.name AS table_name, COUNT(*) AS column_count
FROM sqlite_master m
JOIN pragma_table_info(m.name) ON 1=1
WHERE m.type = 'table'
GROUP BY m.name
ORDER BY m.name;

--  2. USERS
--  ..............................................................................
SELECT id, name, username, email, phone FROM users ORDER BY id;

SELECT id, name,
       substr(address, 1, 50) AS address_preview,
       substr(company, 1, 50) AS company_preview
FROM users ORDER BY id;

--  3. POSTS
--  ..............................................................................
SELECT p.id, p.userId, u.name AS author, substr(p.title, 1, 50) AS title
FROM posts p
JOIN users u ON u.id = p.userId
ORDER BY p.id;

SELECT u.id, u.name, COUNT(p.id) AS post_count
FROM users u
LEFT JOIN posts p ON p.userId = u.id
GROUP BY u.id
ORDER BY post_count DESC;

--  4. COMMENTS
--  ..............................................................................
SELECT c.id, c.postId, c.name, c.email, substr(c.body, 1, 40) AS body_preview
FROM comments c
ORDER BY c.id
LIMIT 10;

SELECT postId, COUNT(*) AS comment_count
FROM comments
GROUP BY postId
ORDER BY postId;

--  5. ALBUMS & PHOTOS
--  ..............................................................................
SELECT a.id, a.userId, u.name AS owner, a.title
FROM albums a
JOIN users u ON u.id = a.userId
ORDER BY a.id;

SELECT a.id, a.title, COUNT(p.id) AS photo_count
FROM albums a
LEFT JOIN photos p ON p.albumId = a.id
GROUP BY a.id
ORDER BY a.id;

SELECT id, albumId, substr(title, 1, 40) AS title, url
FROM photos
ORDER BY id
LIMIT 10;

--  6. TODOS
--  ..............................................................................
SELECT t.id, t.userId, u.name AS user, substr(t.title, 1, 40) AS title, t.completed
FROM todos t
JOIN users u ON u.id = t.userId
ORDER BY t.id;

SELECT u.name,
       COUNT(t.id) AS total,
       SUM(CASE WHEN t.completed THEN 1 ELSE 0 END) AS done,
       SUM(CASE WHEN NOT t.completed THEN 1 ELSE 0 END) AS pending
FROM users u
LEFT JOIN todos t ON t.userId = u.id
GROUP BY u.id
ORDER BY u.id;

--  7. RELATIONSHIPS & INTEGRITY
--  ..............................................................................
SELECT u.id, u.name,
       COUNT(DISTINCT p.id) AS posts,
       COUNT(DISTINCT c.id) AS comments_on_posts,
       COUNT(DISTINCT a.id) AS albums,
       COUNT(DISTINCT t.id) AS todos
FROM users u
LEFT JOIN posts p  ON p.userId = u.id
LEFT JOIN comments c ON c.postId IN (SELECT id FROM posts WHERE userId = u.id)
LEFT JOIN albums a  ON a.userId = u.id
LEFT JOIN todos t   ON t.userId = u.id
GROUP BY u.id
ORDER BY u.id;

SELECT 'posts' AS tbl, 'userId' AS col, p.userId AS val
FROM posts p LEFT JOIN users u ON u.id = p.userId WHERE u.id IS NULL
UNION ALL
SELECT 'comments', 'postId', c.postId
FROM comments c LEFT JOIN posts p ON p.id = c.postId WHERE p.id IS NULL
UNION ALL
SELECT 'albums', 'userId', a.userId
FROM albums a LEFT JOIN users u ON u.id = a.userId WHERE u.id IS NULL;

--  8. SETTINGS
--  ..............................................................................
SELECT id, key, value, description, updated_at FROM settings ORDER BY key;

--  9. STATISTICS
--  ..............................................................................
SELECT 'posts' AS type, AVG(LENGTH(body)) AS avg_len, MIN(LENGTH(body)) AS min_len, MAX(LENGTH(body)) AS max_len FROM posts
UNION ALL
SELECT 'comments', AVG(LENGTH(body)), MIN(LENGTH(body)), MAX(LENGTH(body)) FROM comments;

SELECT CASE WHEN completed THEN 'done' ELSE 'pending' END AS status,
       COUNT(*) AS count,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM todos), 1) AS pct
FROM todos GROUP BY completed;

SELECT 'user_activity' AS metric, MAX(pc) || ' posts' AS value FROM (SELECT userId, COUNT(*) AS pc FROM posts GROUP BY userId)
UNION ALL
SELECT 'user_activity', MAX(ac) || ' albums' FROM (SELECT userId, COUNT(*) AS ac FROM albums GROUP BY userId)
UNION ALL
SELECT 'user_activity', MAX(tc) || ' todos'  FROM (SELECT userId, COUNT(*) AS tc FROM todos GROUP BY userId);
