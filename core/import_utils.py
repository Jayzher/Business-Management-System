"""
Reusable CSV import infrastructure.
Provides base classes and helpers for importing CSV data into Django models.
"""
import csv
import io
import traceback
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse


def parse_csv_upload(uploaded_file):
    """Parse an uploaded CSV file and return (headers, rows) or raise ValueError."""
    if not uploaded_file:
        raise ValueError('No file was uploaded.')
    if not uploaded_file.name.lower().endswith('.csv'):
        raise ValueError('Only CSV files are accepted.')
    try:
        decoded = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            uploaded_file.seek(0)
            decoded = uploaded_file.read().decode('latin-1')
        except Exception:
            raise ValueError('Could not decode the file. Please save it as UTF-8 CSV.')

    reader = csv.DictReader(io.StringIO(decoded))
    headers = reader.fieldnames or []
    rows = list(reader)
    if not rows:
        raise ValueError('The CSV file is empty (no data rows found).')
    return headers, rows


def normalize_header(h):
    """Normalize a CSV header to lowercase, stripped, underscored."""
    return h.strip().lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '').replace('%', 'pct').replace('#', 'no')


def build_header_map(csv_headers, field_map):
    """
    Build a mapping from normalized CSV header → model field name.
    field_map: dict of { 'csv_column_name_normalized': 'model_field_name' }
    Returns dict of { csv_original_header: model_field_name }
    """
    result = {}
    normalized = {normalize_header(h): h for h in csv_headers}
    for csv_key, model_field in field_map.items():
        norm = normalize_header(csv_key)
        if norm in normalized:
            result[normalized[norm]] = model_field
    return result


def safe_decimal(value, default=Decimal('0')):
    """Safely convert a value to Decimal."""
    if not value or str(value).strip() == '':
        return default
    try:
        cleaned = str(value).strip().replace(',', '').replace('₱', '').replace('PHP', '').replace('php', '').strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return default


def safe_date(value, formats=None):
    """Safely parse a date string. Returns date or None."""
    if not value or str(value).strip() == '':
        return None
    formats = formats or [
        '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y',
        '%m/%d/%y', '%d-%m-%Y', '%B %d, %Y', '%b %d, %Y',
        '%Y/%m/%d',
    ]
    val = str(value).strip()
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def safe_int(value, default=0):
    """Safely convert to int."""
    try:
        return int(Decimal(str(value).strip().replace(',', '')))
    except (InvalidOperation, ValueError, TypeError):
        return default


def generate_csv_template(columns, filename):
    """
    Generate an HTTP response with a CSV template.

    columns: list of column header strings
    filename: e.g. 'catalog_items_template.csv'
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)

    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


class ImportResult:
    """Tracks import results for display."""
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors = []   # list of dicts: {row_num, message, row_data}
        self.warnings = [] # list of plain strings

    @property
    def total_processed(self):
        return self.created + self.updated + self.skipped

    @property
    def success_count(self):
        return self.created + self.updated

    def add_error(self, row_num, message, row_data=None):
        self.errors.append({
            'row_num': row_num,
            'message': message,
            'row_data': row_data or {},
        })

    def add_warning(self, row_num, message):
        self.warnings.append(f"Row {row_num}: {message}")

    def to_dict(self):
        return {
            'created': self.created,
            'updated': self.updated,
            'skipped': self.skipped,
            'total_processed': self.total_processed,
            'success_count': self.success_count,
            'errors': self.errors,
            'warnings': self.warnings,
        }
