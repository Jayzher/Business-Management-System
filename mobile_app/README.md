# Business Management System — Mobile App

Flutter + Drift + Custom Sync mobile app for the Business Management System.

## Stack
- **Flutter 3.x** — Cross-platform (iOS / Android)
- **Drift (SQLite)** — Offline-first local database
- **Riverpod** — State management
- **Dio** — HTTP client with JWT refresh
- **GoRouter** — Declarative routing

## Setup

### Prerequisites
- Flutter SDK 3.2+
- Android Studio / Xcode
- Running Django backend

### Install & Run

```bash
cd mobile_app

# Install dependencies
flutter pub get

# Generate Drift database code
dart run build_runner build --delete-conflicting-outputs

# Run on device/emulator
flutter run
```

### Connect to Django Backend

1. Copy `django_sync/sync_views.py` and `django_sync/sync_urls.py` into your Django project
2. Add to `inventory_system/urls.py`:
   ```python
   path('api/sync/', include('sync.urls')),
   ```
3. Update `lib/config/api_config.dart` with your server URL
4. Ensure JWT token endpoints are configured

## Architecture

```
lib/
├── main.dart                  # App entry point
├── app.dart                   # Root widget with lifecycle sync
├── config/                    # Theme, API config, routing
├── database/
│   ├── app_database.dart      # Drift database definition
│   └── tables/                # Table definitions (mirrors Django models)
├── repositories/              # Data access layer (reads from Drift)
├── sync/
│   └── sync_engine.dart       # Push/pull sync with conflict resolution
├── services/                  # API client, auth, connectivity
├── features/                  # Screens organized by module
│   ├── auth/
│   ├── home/
│   ├── catalog/
│   ├── inventory/
│   ├── pos/
│   ├── partners/
│   ├── sales/
│   └── settings/
└── widgets/                   # Shared widgets (sync indicator, offline banner)
```

## Offline Sync Flow

1. **On app start**: Pull all master data (items, categories, units, warehouses, etc.)
2. **During use**: All writes go to local SQLite + sync queue
3. **On connectivity**: Push queued changes → Pull remote updates
4. **Periodic**: Auto-sync every 5 minutes when online
5. **Conflict resolution**: Server wins for master data, local wins for transactions

## Modules

| Module | Status | Offline Support |
|--------|--------|----------------|
| Auth (Login/JWT) | ✅ Scaffolded | Token cached locally |
| Catalog (Items/Units) | ✅ Scaffolded | Full read offline, search by barcode |
| Inventory (Balances) | ✅ Scaffolded | Read offline, local deduction on POS sale |
| POS (Sales) | ✅ Scaffolded | Full offline — create sales, payments, stock deduction |
| Partners | ✅ Scaffolded | Full read offline |
| Sales Orders | 🔲 Placeholder | — |
| Pricing | ✅ DB Ready | Synced price lists, customer pricing |
| Cashflow | ✅ DB Ready | Queue transactions for sync |
| Settings/Sync | ✅ Scaffolded | Manual sync trigger, status display |
