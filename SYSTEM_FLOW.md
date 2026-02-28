# WIS — Warehouse Inventory System: Full System Flow

## Table of Contents
1. [Module Order & Data Dictionary](#1-module-order--data-dictionary)
2. [Document Workflow Summary](#2-document-workflow-summary)
3. [Activity Diagrams (Text-Based)](#3-activity-diagrams-text-based)
4. [Role-Based Access Matrix](#4-role-based-access-matrix)
5. [End-to-End Flow Example](#5-end-to-end-flow-example)

---

## 1. Module Order & Data Dictionary

### Module Execution Order (Setup → Operations → Reporting)

| Order | Module        | Purpose                                      | Key Models                              |
|-------|---------------|----------------------------------------------|-----------------------------------------|
| 1     | **Catalog**   | Master data: items, categories, units        | Item, Category, Unit, UnitConversion    |
| 2     | **Pricing**   | Price lists, discount rules                  | PriceList, PriceListItem, DiscountRule  |
| 3     | **Partners**  | Suppliers and customers                      | Supplier, Customer                      |
| 4     | **Warehouses**| Storage locations                            | Warehouse, Location                     |
| 5     | **Procurement** | Inbound purchasing                         | PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine |
| 6     | **Inventory** | Stock operations                             | StockTransfer, StockAdjustment, DamagedReport, StockMove, StockBalance |
| 7     | **Sales**     | Outbound order fulfillment                   | SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine |
| 8     | **POS**       | Point-of-sale frontline                      | POSRegister, POSShift, POSSale, POSSaleLine, POSPayment, POSRefund |
| 9     | **Core**      | Settings, expenses, supplies, invoices, goals| BusinessProfile, Expense, SupplyItem, Invoice, TargetGoal |
| 10    | **Reports**   | Analytics and output                         | (views only — no models)                |

### Data Flow Path

```
Catalog/Pricing/Partners/Warehouses (masters)
        │
        ▼
Procurement (PO → GRN) ──► stock IN
        │
        ▼
Inventory (Transfer / Adjust / Damaged) ──► stock moves
        │
        ▼
Sales (SO → DN) ──► stock OUT
POS (Sale / Refund) ──► stock OUT / IN
        │
        ▼
Reports (SOH, Movement, Low Stock, Valuation, P&L)
```

---

## 2. Document Workflow Summary

### Status Lifecycle

| Document           | Workflow                              | Has Approve? | Has Post? | Stock Effect        |
|--------------------|---------------------------------------|:------------:|:---------:|---------------------|
| Purchase Order     | DRAFT → APPROVED → (no post)         | ✅           | ❌        | None (order only)   |
| Goods Receipt      | DRAFT → POSTED                        | ❌           | ✅        | +qty to location    |
| Sales Order        | DRAFT → APPROVED → (no post)         | ✅           | ❌        | None (order only)   |
| Delivery Note      | DRAFT → POSTED                        | ❌           | ✅        | −qty from location  |
| Stock Transfer     | DRAFT → POSTED                        | ❌           | ✅        | −from / +to         |
| Stock Adjustment   | DRAFT → APPROVED → POSTED             | ✅           | ✅        | ±qty per difference |
| Damaged Report     | DRAFT → POSTED                        | ❌           | ✅        | −qty (write-off)    |
| POS Sale           | DRAFT → PAID → POSTED                 | ❌           | ✅        | −qty (POS_SALE)     |
| POS Refund         | DRAFT → POSTED                        | ❌           | ✅        | +qty (RETURN_IN)    |

**All documents** can be CANCELLED from any non-cancelled state. If POSTED, cancellation creates reversal StockMoves.

### Status Definitions

| Status      | Meaning                                                        |
|-------------|----------------------------------------------------------------|
| DRAFT       | Created but not committed. Editable and deletable.             |
| APPROVED    | Reviewed and locked. Cannot be edited. Ready for posting.      |
| POSTED      | Committed. Stock balances updated. Immutable.                  |
| CANCELLED   | Voided. If was POSTED, reversal moves created automatically.   |

---

## 3. Activity Diagrams (Text-Based)

### 3.1 Procurement Flow (PO → GRN)

```
[Start]
   │
   ▼
[Create Purchase Order (DRAFT)]
   │
   ▼
[Add/Edit PO Lines: item, qty, unit, price]
   │
   ▼
[Review PO] ──► [Approve PO] ──► status = APPROVED
   │                                    │
   │                                    ▼
   │                          [Create Goods Receipt (DRAFT)]
   │                                    │
   │                                    ▼
   │                          [Add GRN Lines: item, location, qty]
   │                                    │
   │                                    ▼
   │                          [Post GRN] ──► status = POSTED
   │                                    │
   │                                    ▼
   │                          [StockMove RECEIVE created]
   │                          [StockBalance +qty at location]
   │                          [PO line qty_received updated]
   │                                    │
   ▼                                    ▼
[Cancel PO?] ──► CANCELLED         [End]
```

### 3.2 Sales Flow (SO → DN)

```
[Start]
   │
   ▼
[Create Sales Order (DRAFT)]
   │
   ▼
[Add/Edit SO Lines: item, qty, unit, price]
   │
   ▼
[Review SO] ──► [Approve SO] ──► status = APPROVED
   │                                    │
   │                                    ▼
   │                          [Reserve Stock (optional)]
   │                                    │
   │                                    ▼
   │                          [Create Delivery Note (DRAFT)]
   │                                    │
   │                                    ▼
   │                          [Add DN Lines: item, location, qty]
   │                                    │
   │                                    ▼
   │                          [Post DN] ──► status = POSTED
   │                                    │
   │                                    ▼
   │                          [StockMove DELIVER created]
   │                          [StockBalance −qty at location]
   │                          [SO line qty_delivered updated]
   │                                    │
   ▼                                    ▼
[Cancel SO?] ──► CANCELLED         [End]
```

### 3.3 Stock Transfer Flow

```
[Start]
   │
   ▼
[Create Transfer (DRAFT)]
   │
   ▼
[Add Lines: item, from_location, to_location, qty]
   │
   ▼
[Post Transfer] ──► status = POSTED
   │
   ▼
[StockMove TRANSFER created]
[StockBalance −qty at from_location]
[StockBalance +qty at to_location]
   │
   ▼
[End]
```

### 3.4 Stock Adjustment Flow

```
[Start]
   │
   ▼
[Create Adjustment (DRAFT)]
   │
   ▼
[Add Lines: item, location, qty_system, qty_counted]
   │
   ▼
[Approve Adjustment] ──► status = APPROVED
   │
   ▼
[Post Adjustment] ──► status = POSTED
   │
   ▼
[For each line: diff = qty_counted − qty_system]
[StockMove ADJUST created per non-zero diff]
[StockBalance ±diff at location]
   │
   ▼
[End]
```

### 3.5 Damaged Report Flow

```
[Start]
   │
   ▼
[Create Damaged Report (DRAFT)]
   │
   ▼
[Add Lines: item, location, qty, reason, photo]
   │
   ▼
[Post Report] ──► status = POSTED
   │
   ▼
[StockMove DAMAGE created]
[StockBalance −qty at location]
   │
   ▼
[End]
```

### 3.6 POS Sale Flow

```
[Start]
   │
   ▼
[Open Shift: register, opening_cash]
   │
   ▼
[POS Terminal: scan/add items to cart]
   │
   ▼
[Apply discounts / price list lookup]
   │
   ▼
[Set Payments: cash, GCash, card, etc.]
   │
   ▼
[Mark Paid] ──► status = PAID
   │
   ▼
[Post Sale] ──► status = POSTED
   │
   ▼
[StockMove POS_SALE created per line]
[StockBalance −qty at register location]
   │
   ▼
[Print Receipt / Generate Invoice]
   │
   ▼
[Close Shift: declare closing cash, calculate variance]
   │
   ▼
[End]
```

### 3.7 POS Refund Flow

```
[Start]
   │
   ▼
[Select original POSTED sale]
   │
   ▼
[Create Refund (DRAFT): select lines to return]
   │
   ▼
[Post Refund] ──► status = POSTED
   │
   ▼
[StockMove RETURN_IN created per line]
[StockBalance +qty at location]
[Original sale status → REFUNDED]
   │
   ▼
[End]
```

### 3.8 Document Cancellation Flow

```
[Start]
   │
   ▼
[Select document (any status except CANCELLED)]
   │
   ▼
[Click Cancel]
   │
   ├── If DRAFT or APPROVED:
   │      └── Set status = CANCELLED
   │
   └── If POSTED:
          ├── Create reversal StockMoves (swap from/to)
          ├── Reverse StockBalance effects
          └── Set status = CANCELLED
   │
   ▼
[End]
```

---

## 4. Role-Based Access Matrix

### Roles

| Role                  | Description                                                    |
|-----------------------|----------------------------------------------------------------|
| **Admin**             | Full system access. User/role management, settings, all modules.|
| **Manager**           | Approve/post documents, view reports, manage catalog/partners. |
| **Procurement Officer** | Create/edit/approve POs and GRNs. View catalog and partners. |
| **Sales Officer**     | Create/edit/approve SOs and DNs. View catalog, partners, inventory.|
| **Warehouse Staff**   | Create/edit transfers, adjustments, damaged reports. Receive goods.|
| **POS Cashier**       | Operate POS terminal, shifts, sales, refunds. POS module only. |

### Access Matrix

| Module / Action              | Admin | Manager | Procurement | Sales | Warehouse | POS Cashier |
|------------------------------|:-----:|:-------:|:-----------:|:-----:|:---------:|:-----------:|
| **Dashboard**                | ✅    | ✅      | ✅          | ✅    | ✅        | ✅          |
| **Catalog** (view)           | ✅    | ✅      | ✅          | ✅    | ✅        | ✅          |
| **Catalog** (create/edit)    | ✅    | ✅      | ❌          | ❌    | ❌        | ❌          |
| **Partners** (view)          | ✅    | ✅      | ✅          | ✅    | ❌        | ❌          |
| **Partners** (create/edit)   | ✅    | ✅      | ❌          | ❌    | ❌        | ❌          |
| **Warehouses** (view)        | ✅    | ✅      | ✅          | ✅    | ✅        | ❌          |
| **Warehouses** (create/edit) | ✅    | ✅      | ❌          | ❌    | ❌        | ❌          |
| **Purchase Orders**          | ✅    | ✅      | ✅          | ❌    | ❌        | ❌          |
| **Goods Receipts**           | ✅    | ✅      | ✅          | ❌    | ✅*       | ❌          |
| **Sales Orders**             | ✅    | ✅      | ❌          | ✅    | ❌        | ❌          |
| **Delivery Notes**           | ✅    | ✅      | ❌          | ✅    | ❌        | ❌          |
| **Stock Transfers**          | ✅    | ✅      | ❌          | ❌    | ✅        | ❌          |
| **Stock Adjustments**        | ✅    | ✅      | ❌          | ❌    | ✅        | ❌          |
| **Damaged Reports**          | ✅    | ✅      | ❌          | ❌    | ✅        | ❌          |
| **Stock Moves** (view)       | ✅    | ✅      | ❌          | ❌    | ✅        | ❌          |
| **POS Terminal**             | ✅    | ✅      | ❌          | ❌    | ❌        | ✅          |
| **POS Shifts**               | ✅    | ✅      | ❌          | ❌    | ❌        | ✅          |
| **POS Receipts**             | ✅    | ✅      | ❌          | ❌    | ❌        | ✅          |
| **Pricing**                  | ✅    | ✅      | ❌          | ❌    | ❌        | ❌          |
| **Reports**                  | ✅    | ✅      | ❌          | ❌    | ❌        | ❌          |
| **Settings**                 | ✅    | ❌      | ❌          | ❌    | ❌        | ❌          |
| **User Management**          | ✅    | ❌      | ❌          | ❌    | ❌        | ❌          |
| **Approve** documents        | ✅    | ✅      | ✅†         | ✅†   | ❌        | ❌          |
| **Post** documents           | ✅    | ✅      | ✅†         | ✅†   | ✅†       | ❌          |
| **Cancel** documents         | ✅    | ✅      | ✅†         | ✅†   | ✅†       | ❌          |

*✅\* = Warehouse Staff can receive goods (GRN) as part of warehouse operations*
*✅† = Only within their own module scope*

### Decorator Mapping

| Decorator            | Roles Allowed                                |
|----------------------|----------------------------------------------|
| `@admin_required`    | Admin                                        |
| `@manager_or_admin_required` | Admin, Manager                       |
| `@procurement_access`| Admin, Manager, Procurement Officer          |
| `@sales_access`      | Admin, Manager, Sales Officer                |
| `@warehouse_access`  | Admin, Manager, Warehouse Staff              |
| `@pos_access`        | Admin, Manager, POS Cashier                  |

---

## 5. End-to-End Flow Example

### Scenario: Purchase → Stock → Sale

```
1. SETUP (one-time)
   ├── Admin creates Categories, Units, Items in Catalog
   ├── Admin creates Suppliers, Customers in Partners
   ├── Admin creates Warehouses, Locations
   └── Admin creates Price Lists, Discount Rules

2. PROCUREMENT
   ├── Procurement Officer creates PO (DRAFT)
   │     └── Adds lines: Item A ×100, Item B ×50
   ├── Manager approves PO → APPROVED
   ├── Warehouse Staff creates GRN linked to PO (DRAFT)
   │     └── Adds lines: Item A ×100 @ Location-A1
   └── Warehouse Staff posts GRN → POSTED
         └── StockBalance: Item A @ Location-A1 = +100

3. INVENTORY OPERATIONS (as needed)
   ├── Transfer: move Item A ×20 from Location-A1 to Location-B1
   ├── Adjustment: physical count shows Item A = 78 (system says 80)
   │     └── Manager approves → Staff posts → balance corrected
   └── Damaged: Item A ×2 damaged → posted → balance −2

4. SALES
   ├── Sales Officer creates SO for Customer X (DRAFT)
   │     └── Adds lines: Item A ×30
   ├── Manager approves SO → APPROVED
   ├── Sales Officer creates DN linked to SO (DRAFT)
   │     └── Adds lines: Item A ×30 from Location-A1
   └── Sales Officer posts DN → POSTED
         └── StockBalance: Item A @ Location-A1 = −30

5. POS (parallel path)
   ├── Cashier opens shift at Register-1
   ├── Customer walks in → scan Item A ×2
   ├── Apply price list → set payment (Cash ₱500)
   ├── Mark paid → Post sale → stock −2
   └── Close shift → declare cash → variance calculated

6. REPORTS
   ├── Stock on Hand: current balances per item/location
   ├── Stock Movement: all moves for a date range
   ├── Low Stock: items below reorder point
   ├── Inventory Valuation: total value of on-hand stock
   ├── Sales Report: revenue by period/channel
   ├── Expense Report: costs by category
   ├── Profit Margin: revenue vs COGS
   └── Financial Statement: income vs expenses
```

---

## Appendix: Management Commands

| Command              | Purpose                                      |
|----------------------|----------------------------------------------|
| `python manage.py seed_data`  | Seed sample master data              |
| `python manage.py seed_roles` | Create default roles (Admin, Manager, Procurement Officer, Sales Officer, Warehouse Staff, POS Cashier) |

## Appendix: Key Backend Services

| Service                    | File                      | Purpose                              |
|----------------------------|---------------------------|--------------------------------------|
| `post_goods_receipt()`     | `inventory/services.py`   | Post GRN → RECEIVE moves + balance   |
| `post_delivery()`          | `inventory/services.py`   | Post DN → DELIVER moves + balance    |
| `post_transfer()`          | `inventory/services.py`   | Post Transfer → TRANSFER moves       |
| `post_adjustment()`        | `inventory/services.py`   | Post Adjustment → ADJUST moves       |
| `post_damaged_report()`    | `inventory/services.py`   | Post Damaged → DAMAGE moves          |
| `cancel_document()`        | `inventory/services.py`   | Cancel any doc, reverse if POSTED    |
| `reserve_stock()`          | `inventory/services.py`   | Reserve stock for SO                 |
| `post_pos_sale()`          | `pos/services/checkout.py`| Post POS sale → POS_SALE moves       |
| `post_pos_refund()`        | `pos/services/checkout.py`| Post refund → RETURN_IN moves        |
| `void_sale()`              | `pos/services/checkout.py`| Void posted sale → reversal moves    |
| `open_shift()`             | `pos/services/checkout.py`| Open POS shift                       |
| `close_shift()`            | `pos/services/checkout.py`| Close shift + cash variance          |
