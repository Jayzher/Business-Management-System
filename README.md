# Business Management System

A comprehensive Django-based business management system with inventory, sales, procurement, POS, and financial management capabilities.

## 📚 Documentation

### API Documentation

- **[Invoice API](INVOICE_API.md)** - REST API for invoice management with pagination, filtering, and search
  - List, detail, summary endpoints
  - Filter by date, payment status, customer
  - Full-text search and ordering
  - JWT authentication

### System Features

- **[Sales Order Synchronization](SALES_ORDER_SYNC.md)** - Automatic sync system for Sales Orders
  - Auto-updates invoices when SO changes
  - Syncs delivery notes and pickups
  - Audit trail for all changes
  - Manual sync commands available

## 🚀 Quick Start

### Run the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start server
python manage.py runserver
```

### Access the System

- **Web Interface:** http://localhost:8000/
- **Admin Panel:** http://localhost:8000/admin/
- **API Root:** http://localhost:8000/api/
- **Invoice API:** http://localhost:8000/api/invoices/

## 🔑 Authentication

### Get JWT Token

```bash
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'
```

### Use Token in API Requests

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/invoices/
```

## 🧪 Testing

### Run Tests

```bash
# Test Invoice API
python manage.py shell < test_invoice_api.py

# Test Sales Order Sync
python manage.py shell < test_sales_order_sync.py

# Run all Django tests
python manage.py test
```

## 📦 Key Features

### Inventory Management
- Multi-warehouse support
- Stock tracking and reservations
- Stock transfers and adjustments
- Damaged goods reporting
- QR code integration

### Sales Management
- Sales orders with multiple fulfillment types
- Delivery notes and pickups
- Sales returns
- Price lists and discounts
- Customer management

### Procurement
- Purchase orders
- Goods receipt notes
- Supplier management
- Cost tracking

### Point of Sale (POS)
- POS registers and shifts
- Sales transactions
- Refunds and returns
- Cash management

### Financial Management
- Invoice generation and tracking
- Payment recording
- Expense management
- Cash flow tracking
- Financial reporting

### Audit & Compliance
- Comprehensive audit logs
- Manual change tracking
- User activity monitoring

## 🔧 Management Commands

### Sales Order Sync

```bash
# Sync specific Sales Order
python manage.py sync_sales_orders --sales-order SO-001

# Sync all Sales Orders
python manage.py sync_sales_orders --all

# Dry run
python manage.py sync_sales_orders --all --dry-run
```

### Other Commands

```bash
# Calculate financial statements
python manage.py calculate_financial_statements

# Rebuild cashflow balances
python manage.py rebuild_cashflow_balances

# Sync invoice COGS
python manage.py sync_invoice_cogs
```

## 📁 Project Structure

```
Business-Management-System/
├── accounts/           # User management and authentication
├── audit/              # Audit logging
├── catalog/            # Product catalog
├── cashflow/           # Financial management
├── core/               # Core models (Invoice, Expense, etc.)
├── inventory/          # Inventory management
├── partners/           # Suppliers and customers
├── pos/                # Point of sale
├── pricing/            # Price lists and discounts
├── procurement/        # Purchase orders and receipts
├── qr/                 # QR code management
├── reports/            # Reporting
├── sales/              # Sales orders and deliveries
├── services/           # Customer services
├── sync/               # Mobile sync
├── theme/              # UI theme
├── warehouses/         # Warehouse management
└── inventory_system/   # Main project settings
```

## 🛠️ Technology Stack

- **Backend:** Django 4.x
- **API:** Django REST Framework
- **Database:** PostgreSQL / SQLite
- **Authentication:** JWT (djangorestframework-simplejwt)
- **Filtering:** django-filter
- **Frontend:** Bootstrap, jQuery
- **Real-time:** Django Channels (WebSocket)

## 📊 API Endpoints

### Core APIs

- `/api/invoices/` - Invoice management
- `/api/expenses/` - Expense tracking
- `/api/sales-orders/` - Sales order management
- `/api/items/` - Product catalog
- `/api/stock-balances/` - Inventory levels
- `/api/purchase-orders/` - Procurement
- `/api/pos/sales/` - POS transactions

### Authentication

- `/api/auth/token/` - Get JWT token
- `/api/auth/token/refresh/` - Refresh token
- `/api/users/me/` - Current user info

## 🔐 Security

- JWT token-based authentication
- Role-based access control (RBAC)
- Warehouse-level permissions
- Audit logging for all transactions
- CSRF protection
- SQL injection prevention

## 📝 License

Proprietary - All rights reserved

## 🤝 Support

For issues or questions:
1. Check the documentation files
2. Review audit logs for errors
3. Check Django logs
4. Run test suites

---

**Version:** 1.0  
**Last Updated:** 2026-05-31
