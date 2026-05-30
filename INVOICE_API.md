# Invoice API Documentation

## Overview

A comprehensive REST API for Invoice management with Django REST Framework (DRF), featuring pagination, filtering, search, and ordering capabilities.

**Base URL:** `/api/invoices/`  
**Authentication:** JWT Token (Bearer)  
**Pagination:** 25 items per page (default)

---

## Quick Start

### 1. Get Authentication Token

```bash
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'
```

### 2. Use the API

```bash
# List invoices
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/invoices/

# Get invoice detail
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/invoices/1/

# Filter unpaid invoices
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/invoices/?is_paid=false"
```

---

## Endpoints

### List Invoices
**GET** `/api/invoices/`

Returns paginated list of all invoices.

**Query Parameters:**

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `page` | integer | Page number | `?page=2` |
| `page_size` | integer | Items per page | `?page_size=50` |
| `date_from` | date | Filter by date >= | `?date_from=2026-01-01` |
| `date_to` | date | Filter by date <= | `?date_to=2026-12-31` |
| `is_paid` | boolean | Payment status | `?is_paid=true` |
| `is_void` | boolean | Void status | `?is_void=false` |
| `customer` | string | Customer name search | `?customer=ABC` |
| `invoice_number` | string | Invoice number search | `?invoice_number=001` |
| `search` | string | Full-text search | `?search=ABC` |
| `ordering` | string | Sort results | `?ordering=-date` |

**Response:**
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/invoices/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "invoice_number": "000001",
      "date": "2026-05-30",
      "customer_name": "ABC Corporation",
      "grand_total": "1500.00",
      "payment_status": "PAID",
      "is_paid": true,
      "is_void": false
    }
  ]
}
```

### Get Invoice Detail
**GET** `/api/invoices/{id}/`

Returns detailed invoice with line items and payments.

**Response:**
```json
{
  "id": 1,
  "invoice_number": "000001",
  "customer_name": "ABC Corporation",
  "grand_total": "1500.00",
  "lines": [
    {
      "item_code": "ITEM-001",
      "item_name": "Product A",
      "qty": "10.0000",
      "line_total": "1000.00"
    }
  ],
  "payments": [
    {
      "date": "2026-05-30",
      "method": "CASH",
      "amount": "1500.00"
    }
  ]
}
```

### Get Summary Statistics
**GET** `/api/invoices/summary/`

Returns invoice summary statistics.

**Response:**
```json
{
  "total_count": 150,
  "total_amount": "250000.00",
  "paid_count": 120,
  "paid_amount": "200000.00",
  "unpaid_count": 25,
  "unpaid_amount": "45000.00",
  "void_count": 5
}
```

### List Unpaid Invoices
**GET** `/api/invoices/unpaid/`

Returns paginated list of unpaid invoices.

### List Overdue Invoices
**GET** `/api/invoices/overdue/`

Returns paginated list of overdue invoices (unpaid with past due date).

---

## Code Examples

### JavaScript (Fetch)

```javascript
// Get unpaid invoices
async function getUnpaidInvoices() {
  const response = await fetch('/api/invoices/?is_paid=false', {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return await response.json();
}

// Get invoice detail
async function getInvoice(id) {
  const response = await fetch(`/api/invoices/${id}/`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return await response.json();
}
```

### Python (requests)

```python
import requests

base_url = 'http://localhost:8000/api'
headers = {'Authorization': f'Bearer {token}'}

# Get invoices
response = requests.get(
    f'{base_url}/invoices/',
    headers=headers,
    params={'is_paid': False, 'ordering': '-date'}
)
invoices = response.json()

# Get invoice detail
response = requests.get(f'{base_url}/invoices/1/', headers=headers)
invoice = response.json()
```

### React Component

```jsx
function InvoiceList() {
  const [invoices, setInvoices] = useState([]);
  
  useEffect(() => {
    fetch('/api/invoices/?is_paid=false', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(r => r.json())
    .then(data => setInvoices(data.results));
  }, []);
  
  return (
    <table>
      <thead>
        <tr>
          <th>Invoice #</th>
          <th>Customer</th>
          <th>Amount</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {invoices.map(inv => (
          <tr key={inv.id}>
            <td>{inv.invoice_number}</td>
            <td>{inv.customer_name}</td>
            <td>₱{inv.grand_total}</td>
            <td>{inv.payment_status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

---

## Filtering & Search

### Combine Multiple Filters

```bash
# Unpaid invoices for customer in date range, sorted by date
GET /api/invoices/?is_paid=false&customer=ABC&date_from=2026-01-01&ordering=-date

# Search with pagination
GET /api/invoices/?search=ABC&page_size=50&page=2

# Overdue invoices sorted by amount
GET /api/invoices/overdue/?ordering=-grand_total
```

### Ordering Options

- `date` - Invoice date
- `grand_total` - Invoice amount
- `created_at` - Creation timestamp
- `invoice_number` - Invoice number

Prefix with `-` for descending order (e.g., `-date` for newest first).

---

## Testing

### Run Automated Tests

```bash
python manage.py shell < test_invoice_api.py
```

### Manual Testing

```bash
# Start server
python manage.py runserver

# Visit in browser (DRF browsable API)
http://localhost:8000/api/invoices/
```

---

## Implementation Details

### Files Created

- `core/serializers.py` - DRF serializers
- `core/api_views.py` - ViewSets with pagination and filtering
- `inventory_system/urls.py` - API route registration (modified)
- `test_invoice_api.py` - Automated test suite

### Features

✅ Pagination (25 items/page, configurable)  
✅ Filtering (date, payment status, customer, etc.)  
✅ Search (invoice number, customer name, TIN)  
✅ Ordering (date, amount, creation time)  
✅ Authentication (JWT tokens)  
✅ Optimized queries (select_related, prefetch_related)  
✅ Custom endpoints (summary, unpaid, overdue)

### Configuration

Already configured in `settings.py`:

```python
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}
```

---

## Troubleshooting

### 401 Unauthorized
- Check if token is valid
- Token may have expired (get new one)
- Verify header format: `Authorization: Bearer YOUR_TOKEN`

### 404 Not Found
- Check invoice ID exists
- Verify URL is correct

### Empty Results
- Check filters are correct
- Verify data exists in database
- Try without filters first

---

## Performance Tips

1. **Use pagination** - Don't fetch all records at once
2. **Filter on server** - Use query params instead of client-side filtering
3. **Use list endpoint** - Only fetch details when needed
4. **Cache results** - Store frequently accessed data
5. **Limit page size** - Balance between requests and data size

---

**Version:** 1.0  
**Status:** Production Ready  
**Authentication:** JWT (JSON Web Tokens)  
**Framework:** Django REST Framework
