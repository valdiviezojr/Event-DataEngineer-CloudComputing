-- Structural signature of migrations 001, 003 and 004 for the touched tables.
WITH relations AS (
    SELECT c.*, n.nspname
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = %(tenant)s AND c.relname = ANY(%(tables)s)
), signature AS (
    SELECT relname, 'table' AS kind, relkind::text || relpersistence::text ||
        relrowsecurity::text || relforcerowsecurity::text || relispartition::text AS definition
    FROM relations
    UNION ALL
    SELECT r.relname, 'column', a.attname || ' ' ||
        pg_catalog.format_type(a.atttypid, a.atttypmod) || ' ' || a.attnotnull::text ||
        ' ' || a.attgenerated::text || ' ' || a.attidentity::text || ' ' ||
        coalesce(pg_catalog.pg_get_expr(d.adbin, d.adrelid), '') ||
        CASE WHEN a.attcollation = 0 OR a.attcollation = t.typcollation THEN '' ELSE ' custom collation' END
    FROM relations r
    JOIN pg_catalog.pg_attribute a ON a.attrelid = r.oid
    JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
    LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = r.oid AND d.adnum = a.attnum
    WHERE a.attnum > 0 AND NOT a.attisdropped
    UNION ALL
    SELECT r.relname, 'constraint', c.conname || ' ' ||
        pg_catalog.pg_get_constraintdef(c.oid) || ' ' || c.convalidated::text
    FROM relations r JOIN pg_catalog.pg_constraint c ON c.conrelid = r.oid
    WHERE c.contype <> 'n'
    UNION ALL
    SELECT r.relname, 'index', pg_catalog.pg_get_indexdef(i.indexrelid) ||
        ' ' || i.indisvalid::text || ' ' || i.indisready::text
    FROM relations r JOIN pg_catalog.pg_index i ON i.indrelid = r.oid
    UNION ALL
    SELECT r.relname, 'trigger', t.tgname
    FROM relations r JOIN pg_catalog.pg_trigger t ON t.tgrelid = r.oid
    WHERE NOT t.tgisinternal OR t.tgenabled <> 'O'
    UNION ALL
    SELECT r.relname, 'rule', w.rulename
    FROM relations r JOIN pg_catalog.pg_rewrite w ON w.ev_class = r.oid
    UNION ALL
    SELECT r.relname, 'publication', p.pubname
    FROM relations r JOIN pg_catalog.pg_publication_tables p
      ON p.schemaname = r.nspname AND p.tablename = r.relname
    UNION ALL
    SELECT r.relname, 'inheritance', i.inhrelid::text
    FROM relations r JOIN pg_catalog.pg_inherits i ON r.oid IN (i.inhparent, i.inhrelid)
)
SELECT relname, kind, replace(definition, %(tenant)s, 'tenant_X') AS normalized
FROM signature ORDER BY relname COLLATE "C", kind COLLATE "C", replace(definition, %(tenant)s, 'tenant_X') COLLATE "C"
