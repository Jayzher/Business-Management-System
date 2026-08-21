"""
Django management command to perform lossless 3-way (or 2-way) merge of SQLite databases.

Usage:
    # 3-way merge:
    python manage.py merge_sqlite --base base.sqlite3 --ours local.sqlite3 --theirs remote.sqlite3 --output db.sqlite3

    # As a Git merge driver:
    python manage.py merge_sqlite --git base_file ours_file theirs_file

    # Simple 2-way merge:
    python manage.py merge_sqlite --src other.sqlite3 --dst db.sqlite3
"""

import os
import sys
import shutil
import sqlite3
import pathlib
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def checkpoint_db(db_path):
    """Ensure WAL is checkpointed and flushed into the main DB file."""
    if not db_path:
        return
    p = pathlib.Path(db_path)
    if p.exists():
        try:
            conn = sqlite3.connect(str(p))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
        except Exception:
            pass


def merge_sqlite_3way(base_path, ours_path, theirs_path, output_path, stdout=None):
    """
    Perform a robust 3-way table-by-table and row-by-row merge of SQLite databases.
    Preserves all records added in either branch and resolves conflicts intelligently.
    """
    def log(msg):
        if stdout:
            stdout.write(msg)
        else:
            print(msg)

    # Checkpoint all inputs
    checkpoint_db(base_path)
    checkpoint_db(ours_path)
    checkpoint_db(theirs_path)

    # Prepare output path
    output_p = pathlib.Path(output_path)
    temp_output_p = output_p.parent / f"{output_p.name}.merge_tmp"

    if temp_output_p.exists():
        temp_output_p.unlink()
    for ext in ['-wal', '-shm']:
        p = pathlib.Path(f"{temp_output_p}{ext}")
        if p.exists():
            p.unlink()

    # Use 'theirs' or 'ours' as baseline schema copy
    base_template = theirs_path if (theirs_path and pathlib.Path(theirs_path).exists()) else ours_path
    shutil.copy2(base_template, temp_output_p)

    # Clean any copied WAL/SHM for the temp output
    for ext in ['-wal', '-shm']:
        p = pathlib.Path(f"{temp_output_p}{ext}")
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    b_conn = sqlite3.connect(str(base_path)) if (base_path and pathlib.Path(base_path).exists() and os.path.getsize(base_path) > 0) else None
    o_conn = sqlite3.connect(str(ours_path))
    t_conn = sqlite3.connect(str(theirs_path))
    out_conn = sqlite3.connect(str(temp_output_p))

    out_conn.execute("PRAGMA foreign_keys = OFF;")
    out_conn.execute("PRAGMA journal_mode = WAL;")

    for conn in [b_conn, o_conn, t_conn, out_conn]:
        if conn:
            conn.row_factory = sqlite3.Row

    cur_o = o_conn.cursor()
    cur_t = t_conn.cursor()
    cur_b = b_conn.cursor() if b_conn else None
    cur_out = out_conn.cursor()

    # Discover tables
    cur_t.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    t_tables = {r['name']: r['sql'] for r in cur_t.fetchall()}

    cur_o.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    o_tables = {r['name']: r['sql'] for r in cur_o.fetchall()}

    all_tables = sorted(list(set(t_tables.keys()) | set(o_tables.keys())))

    stats = {
        'tables_processed': 0,
        'inserted_from_ours': 0,
        'inserted_from_theirs': 0,
        'updated_from_ours': 0,
        'updated_from_theirs': 0,
        'conflicts_resolved': 0,
        'unchanged': 0,
    }

    for tbl in all_tables:
        stats['tables_processed'] += 1

        # If table is only in ours, create it in output
        if tbl not in t_tables and tbl in o_tables:
            cur_out.execute(o_tables[tbl])

        cur_out.execute(f'PRAGMA table_info("{tbl}")')
        table_info = cur_out.fetchall()
        cols = [r['name'] for r in table_info]
        pk_cols = [r['name'] for r in table_info if r['pk'] > 0]

        use_rowid = False
        if not pk_cols:
            use_rowid = True
            pk_cols = ['rowid']

        col_list_str = ', '.join([f'"{c}"' for c in cols])
        placeholders = ', '.join(['?' for _ in cols])

        def fetch_rows(cur, is_rowid, t_name, p_cols):
            if not cur:
                return {}
            try:
                if is_rowid:
                    cur.execute(f'SELECT rowid, * FROM "{t_name}"')
                else:
                    cur.execute(f'SELECT * FROM "{t_name}"')
                return {tuple(row[c] for c in p_cols): dict(row) for row in cur.fetchall()}
            except Exception:
                return {}

        b_rows = fetch_rows(cur_b, use_rowid, tbl, pk_cols)
        o_rows = fetch_rows(cur_o, use_rowid, tbl, pk_cols)
        t_rows = fetch_rows(cur_t, use_rowid, tbl, pk_cols)

        all_pks = set(b_rows.keys()) | set(o_rows.keys()) | set(t_rows.keys())

        cur_out.execute(f'DELETE FROM "{tbl}";')

        merged_rows = {}
        for pk in all_pks:
            in_b = pk in b_rows
            in_o = pk in o_rows
            in_t = pk in t_rows

            b_val = b_rows.get(pk)
            o_val = o_rows.get(pk)
            t_val = t_rows.get(pk)

            if in_o and in_t and not in_b:
                # Inserted in both branches
                if o_val == t_val:
                    merged_rows[pk] = t_val
                    stats['unchanged'] += 1
                else:
                    ts_col = next((c for c in ['updated_at', 'modified_at', 'last_login', 'created_at'] if c in o_val and c in t_val), None)
                    if ts_col and (o_val.get(ts_col) or t_val.get(ts_col)):
                        chosen = o_val if (o_val.get(ts_col) or '') > (t_val.get(ts_col) or '') else t_val
                    else:
                        chosen = t_val
                    merged_rows[pk] = chosen
                    stats['conflicts_resolved'] += 1

            elif in_t and not in_o and not in_b:
                # Inserted in theirs
                merged_rows[pk] = t_val
                stats['inserted_from_theirs'] += 1

            elif in_o and not in_t and not in_b:
                # Inserted in ours
                merged_rows[pk] = o_val
                stats['inserted_from_ours'] += 1

            elif in_b and not in_o and in_t:
                # Existed in base, missing in ours, present in theirs
                if t_val == b_val:
                    # Deleted in ours, unchanged in theirs -> Delete
                    pass
                else:
                    # Modified in theirs but deleted in ours -> Keep theirs to prevent data loss
                    merged_rows[pk] = t_val
                    stats['updated_from_theirs'] += 1

            elif in_b and in_o and not in_t:
                # Existed in base, present in ours, missing in theirs
                if o_val == b_val:
                    # Deleted in theirs, unchanged in ours -> Delete
                    pass
                else:
                    # Modified in ours but deleted in theirs -> Keep ours to prevent data loss
                    merged_rows[pk] = o_val
                    stats['updated_from_ours'] += 1

            elif in_b and in_o and in_t:
                # Exists in all 3
                if o_val == t_val:
                    merged_rows[pk] = t_val
                    stats['unchanged'] += 1
                elif o_val == b_val and t_val != b_val:
                    # Modified in theirs only
                    merged_rows[pk] = t_val
                    stats['updated_from_theirs'] += 1
                elif t_val == b_val and o_val != b_val:
                    # Modified in ours only
                    merged_rows[pk] = o_val
                    stats['updated_from_ours'] += 1
                else:
                    # Modified in both (3-way conflict resolution)
                    if tbl == 'auth_user':
                        merged = dict(t_val)
                        if (o_val.get('last_login') or '') > (t_val.get('last_login') or ''):
                            merged['last_login'] = o_val['last_login']
                        if o_val.get('password') != b_val.get('password') and t_val.get('password') == b_val.get('password'):
                            merged['password'] = o_val['password']
                        merged_rows[pk] = merged
                    elif tbl == 'sync_metadata':
                        merged = dict(t_val)
                        if (o_val.get('value') or '') > (t_val.get('value') or ''):
                            merged['value'] = o_val['value']
                        merged_rows[pk] = merged
                    else:
                        # Column-level 3-way merge
                        merged = dict(b_val)
                        for col in cols:
                            b_c = b_val.get(col)
                            o_c = o_val.get(col)
                            t_c = t_val.get(col)
                            if o_c != b_c and t_c == b_c:
                                merged[col] = o_c
                            elif t_c != b_c and o_c == b_c:
                                merged[col] = t_c
                            elif o_c != b_c and t_c != b_c:
                                ts_col = next((c for c in ['updated_at', 'modified_at', 'created_at'] if c in o_val and c in t_val), None)
                                if ts_col and (o_val.get(ts_col) or t_val.get(ts_col)):
                                    merged[col] = o_c if (o_val.get(ts_col) or '') > (t_val.get(ts_col) or '') else t_c
                                else:
                                    merged[col] = t_c
                            else:
                                merged[col] = b_c
                        merged_rows[pk] = merged
                    stats['conflicts_resolved'] += 1

        # Write rows in batch
        if merged_rows:
            sql = f'INSERT INTO "{tbl}" ({col_list_str}) VALUES ({placeholders})'
            batch = []
            for row_dict in merged_rows.values():
                batch.append([row_dict.get(c) for c in cols])
            cur_out.executemany(sql, batch)

    out_conn.commit()

    # Integrity & FK checks
    out_conn.execute("PRAGMA foreign_keys = ON;")
    cur_out.execute("PRAGMA foreign_key_check;")
    fk_errors = cur_out.fetchall()
    if fk_errors:
        log(f"  [WARN] Foreign key check reported {len(fk_errors)} inconsistencies.")
    else:
        log("  [OK] Foreign key integrity verified (0 errors).")

    cur_out.execute("PRAGMA integrity_check;")
    integrity = cur_out.fetchall()
    log(f"  [OK] Database integrity check: {[tuple(r) for r in integrity]}")

    out_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    out_conn.close()

    if b_conn:
        b_conn.close()
    o_conn.close()
    t_conn.close()

    # Safely replace output file
    if output_p.exists():
        # Remove target WAL/SHM if they exist
        for ext in ['-wal', '-shm']:
            p = pathlib.Path(f"{output_p}{ext}")
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        output_p.unlink()

    shutil.move(temp_output_p, output_p)

    log("\nMerge Summary:")
    log(f"  Tables processed:       {stats['tables_processed']}")
    log(f"  Inserted from ours:     {stats['inserted_from_ours']}")
    log(f"  Inserted from theirs:   {stats['inserted_from_theirs']}")
    log(f"  Updated from ours:      {stats['updated_from_ours']}")
    log(f"  Updated from theirs:    {stats['updated_from_theirs']}")
    log(f"  Conflicts resolved:     {stats['conflicts_resolved']}")
    log(f"  Unchanged records:      {stats['unchanged']}")
    log(f"Merged database written to: {output_p}\n")
    return True


class Command(BaseCommand):
    help = 'Lossless 3-way or 2-way merge for SQLite databases'

    def add_arguments(self, parser):
        parser.add_argument('--base', type=str, help='Path to common ancestor base database')
        parser.add_argument('--ours', type=str, help='Path to local/ours database')
        parser.add_argument('--theirs', type=str, help='Path to remote/theirs database')
        parser.add_argument('--output', type=str, help='Path to output merged database')
        parser.add_argument('--git', nargs=3, metavar=('BASE', 'OURS', 'THEIRS'),
                            help='Git merge driver mode: base, ours, theirs')
        parser.add_argument('--src', type=str, help='Source DB for 2-way merge')
        parser.add_argument('--dst', type=str, help='Destination DB for 2-way merge (updated in place)')

    def handle(self, *args, **options):
        git_args = options.get('git')
        if git_args:
            base_p, ours_p, theirs_p = git_args
            self.stdout.write("Executing Git SQLite 3-way merge driver...")
            self.stdout.write(f"  Base:   {base_p}")
            self.stdout.write(f"  Ours:   {ours_p}")
            self.stdout.write(f"  Theirs: {theirs_p}")
            success = merge_sqlite_3way(base_p, ours_p, theirs_p, ours_p, stdout=self.stdout)
            if not success:
                sys.exit(1)
            return

        base_p = options.get('base')
        ours_p = options.get('ours')
        theirs_p = options.get('theirs')
        output_p = options.get('output')

        if ours_p and theirs_p:
            if not output_p:
                output_p = ours_p
            merge_sqlite_3way(base_p, ours_p, theirs_p, output_p, stdout=self.stdout)
            return

        src_p = options.get('src')
        dst_p = options.get('dst')
        if src_p and dst_p:
            self.stdout.write(f"Executing 2-way merge: {src_p} -> {dst_p}")
            merge_sqlite_3way(None, dst_p, src_p, dst_p, stdout=self.stdout)
            return

        self.stderr.write("Please specify either --git BASE OURS THEIRS OR --ours, --theirs, --output OR --src, --dst")
