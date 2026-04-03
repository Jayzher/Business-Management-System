"""
Export SQLite data as PostgreSQL-compatible SQL files for Neon SQL Editor.
Tables are ordered by FK dependencies (parents first) so no special permissions needed.
Outputs a single _ALL.sql ready to paste.
"""
import os, sys, sqlite3

# Setup Django so we can inspect model field types
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
import django
django.setup()
from django.apps import apps

DB_PATH = os.path.join(os.path.dirname(__file__), 'db.sqlite3')
OUT_DIR = os.path.join(os.path.dirname(__file__), 'sync')
os.makedirs(OUT_DIR, exist_ok=True)

# Build a map of {table_name: {column_name: is_boolean}}
BOOL_COLS = {}
for model in apps.get_models(include_auto_created=True):
    table = model._meta.db_table
    bools = set()
    for field in model._meta.get_fields():
        if hasattr(field, 'column') and hasattr(field, 'get_internal_type'):
            if field.get_internal_type() in ('BooleanField', 'NullBooleanField'):
                bools.add(field.column)
    if bools:
        BOOL_COLS[table] = bools

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
all_tables = [r[0] for r in cur.fetchall()]

# ── Build FK dependency graph and topological sort ──
def get_fk_deps(cursor, tables):
    """Return {table: set of tables it depends on}."""
    deps = {t: set() for t in tables}
    for t in tables:
        try:
            cursor.execute(f'PRAGMA foreign_key_list("{t}")')
            for row in cursor.fetchall():
                ref = row[2]  # referenced table
                if ref in deps and ref != t:
                    deps[t].add(ref)
        except Exception:
            pass
    return deps

def topo_sort(deps):
    """Topological sort — parents before children."""
    result = []
    visited = set()
    temp = set()
    def visit(node):
        if node in temp:
            return  # cycle, skip
        if node in visited:
            return
        temp.add(node)
        for dep in deps.get(node, []):
            visit(dep)
        temp.discard(node)
        visited.add(node)
        result.append(node)
    for node in sorted(deps.keys()):
        visit(node)
    return result

deps = get_fk_deps(cur, all_tables)
tables = topo_sort(deps)
print(f"Sorted {len(tables)} tables by FK dependencies\n")

def escape_value(val, table=None, col=None):
    if val is None:
        return 'NULL'
    # Check if this column is a boolean field
    if table and col and col in BOOL_COLS.get(table, set()):
        if val in (1, '1', True):
            return 'TRUE'
        return 'FALSE'
    if isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return f"'{s}'"

# ── Generate single _ALL.sql ──
all_path = os.path.join(OUT_DIR, '_ALL.sql')
total_rows = 0
table_stats = []

with open(all_path, 'w', encoding='utf-8') as f:
    f.write("-- Full SQLite -> Neon PostgreSQL migration\n")
    f.write("-- Tables ordered by FK dependencies (parents first)\n")
    f.write("-- No superuser permissions required\n")
    f.write("BEGIN;\n\n")

    for table in tables:
        try:
            cur.execute(f'SELECT * FROM "{table}"')
            rows = cur.fetchall()
        except Exception as e:
            print(f"  SKIP  {table}: {e}")
            continue

        if not rows:
            print(f"  SKIP  {table} (empty)")
            continue

        columns = [desc[0] for desc in cur.description]
        col_list = ', '.join(f'"{c}"' for c in columns)

        f.write(f'-- ── {table} ({len(rows)} rows) ──\n')

        BATCH = 100
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i+BATCH]
            f.write(f'INSERT INTO "{table}" ({col_list}) VALUES\n')
            value_lines = []
            for row in batch:
                vals = ', '.join(escape_value(row[c], table, c) for c in columns)
                value_lines.append(f'  ({vals})')
            f.write(',\n'.join(value_lines))
            f.write('\nON CONFLICT DO NOTHING;\n\n')

        # Reset sequence
        if 'id' in columns:
            f.write(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM \"{table}\"), 1));\n\n")

        total_rows += len(rows)
        table_stats.append((table, len(rows)))
        print(f"  OK    {table}: {len(rows)} rows")

    f.write("COMMIT;\n")

conn.close()

size_kb = round(os.path.getsize(all_path) / 1024)
print(f"\n{'=' * 55}")
print(f"Generated _ALL.sql ({size_kb} KB)")
print(f"Total: {total_rows} rows across {len(table_stats)} tables")
print(f"{'=' * 55}")
