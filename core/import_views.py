"""
CSV Import views for all modules:
  1. Catalog Items
  2. Expenses
  3. Sales Orders
  4. Supply Items (Inventory)
  5. Procurement (Stock-In / Supply Movements)
"""
import traceback
from decimal import Decimal

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, IntegrityError

from core.import_utils import (
    parse_csv_upload, normalize_header, safe_decimal, safe_date,
    safe_int, generate_csv_template, ImportResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. CATALOG ITEMS IMPORT
# ═══════════════════════════════════════════════════════════════════════════

CATALOG_TEMPLATE_COLUMNS = [
    'Product / Service Name', 'Item Code (SKU)', 'Item Type', 'Category',
    'Unit', 'Barcode', 'Description', 'Item Cost', 'Item Selling Price',
    'Minimum Stock', 'Maximum Stock', 'Reorder Point',
]

CATALOG_FIELD_MAP = {
    'product___service_name': 'name',
    'item_code_sku': 'code',
    'item_type': 'item_type',
    'category': 'category',
    'unit': 'unit',
    'barcode': 'barcode',
    'description': 'description',
    'item_cost': 'cost_price',
    'item_selling_price': 'selling_price',
    'minimum_stock': 'minimum_stock',
    'maximum_stock': 'maximum_stock',
    'reorder_point': 'reorder_point',
}


@login_required
def catalog_import_template(request):
    return generate_csv_template(CATALOG_TEMPLATE_COLUMNS, 'catalog_items_template.csv')


@login_required
def catalog_import(request):
    if request.method != 'POST':
        return render(request, 'core/import_modal.html', {
            'title': 'Import Catalog Items',
            'import_url': 'catalog_import',
            'template_url': 'catalog_import_template',
            'cancel_url': '/catalog/items/',
        })

    from catalog.models import Item, Category, Unit, ItemType

    result = ImportResult()
    try:
        headers, rows = parse_csv_upload(request.FILES.get('csv_file'))
    except ValueError as e:
        result.add_error(1, str(e))
        return render(request, 'core/import_summary_modal.html', {
            'result': result,
            'cancel_url': '/catalog/items/',
        })

    # Process each row individually with savepoint to prevent full rollback
    for i, row in enumerate(rows, start=2):
        try:
            with transaction.atomic():
                norm = {normalize_header(k): v.strip() for k, v in row.items() if v}

                code = norm.get('item_code_sku', '').strip()
                name = norm.get('product___service_name', '').strip()
                if not code and not name:
                    result.skipped += 1
                    continue
                if not code:
                    result.add_error(i, 'Item Code (SKU) is required.', row)
                    result.skipped += 1
                    continue

                # Resolve category
                cat_name = norm.get('category', '')
                category = None
                if cat_name:
                    category = Category.objects.filter(name__iexact=cat_name).first()
                    if not category:
                        category = Category.objects.filter(code__iexact=cat_name).first()
                    if not category:
                        cat_code = cat_name[:30].upper().replace(' ', '_')
                        try:
                            category, created_cat = Category.objects.get_or_create(
                                code=cat_code,
                                defaults={'name': cat_name},
                            )
                        except IntegrityError:
                            category = Category.objects.filter(code=cat_code).first()
                            created_cat = False
                        if created_cat:
                            result.add_warning(i, f'Created new category: {cat_name}')

                # Resolve unit
                unit_name = norm.get('unit', 'pcs')
                unit = Unit.objects.filter(abbreviation__iexact=unit_name).first()
                if not unit:
                    unit = Unit.objects.filter(name__iexact=unit_name).first()
                if not unit:
                    abbr = unit_name[:10].lower()
                    try:
                        unit, created_unit = Unit.objects.get_or_create(
                            abbreviation=abbr,
                            defaults={'name': unit_name},
                        )
                    except IntegrityError:
                        unit = Unit.objects.filter(abbreviation=abbr).first()
                        created_unit = False
                    if created_unit:
                        result.add_warning(i, f'Created new unit: {unit_name}')

                # Resolve item type
                item_type_raw = norm.get('item_type', 'RAW').upper()
                if item_type_raw in ('RAW', 'RAW MATERIAL'):
                    item_type = ItemType.RAW
                elif item_type_raw in ('FINISHED', 'FINISHED PRODUCT'):
                    item_type = ItemType.FINISHED
                elif item_type_raw in ('SERVICE',):
                    item_type = ItemType.SERVICE
                else:
                    result.add_error(i, f'Invalid Item Type "{item_type_raw}". Use RAW, FINISHED, or SERVICE.', row)
                    result.skipped += 1
                    continue

                defaults = {
                    'name': name or code,
                    'item_type': item_type,
                    'category': category or Category.objects.first(),
                    'default_unit': unit,
                    'barcode': norm.get('barcode', ''),
                    'description': norm.get('description', ''),
                    'cost_price': safe_decimal(norm.get('item_cost')),
                    'selling_price': safe_decimal(norm.get('item_selling_price')),
                    'minimum_stock': safe_decimal(norm.get('minimum_stock')),
                    'maximum_stock': safe_decimal(norm.get('maximum_stock')),
                    'reorder_point': safe_decimal(norm.get('reorder_point')),
                }

                if not defaults['category']:
                    result.add_error(i, 'No category found and none exists in the system.', row)
                    result.skipped += 1
                    continue

                obj, created = Item.objects.update_or_create(
                    code=code, defaults=defaults
                )
                if created:
                    result.created += 1
                else:
                    result.updated += 1

        except Exception as e:
            result.add_error(i, str(e), row)
            result.skipped += 1

    return render(request, 'core/import_summary_modal.html', {
        'result': result,
        'cancel_url': '/catalog/items/',
    })


# ═══════════════════════════════════════════════════════════════════════════
# 2. EXPENSES IMPORT
# ═══════════════════════════════════════════════════════════════════════════

EXPENSE_TEMPLATE_COLUMNS = [
    'Purchase Date', 'Category', 'Item Description', 'Total Cost', 'Status',
    'Receipt Photo', 'Vendor Name', 'Business Address', 'Reference No', 'Notes',
]

@login_required
def expense_import_template(request):
    return generate_csv_template(EXPENSE_TEMPLATE_COLUMNS, 'expenses_template.csv')


@login_required
def expense_import(request):
    if request.method != 'POST':
        return render(request, 'core/import_modal.html', {
            'title': 'Import Expenses',
            'import_url': 'expense_import',
            'template_url': 'expense_import_template',
            'cancel_url': '/expenses/',
        })

    from core.models import Expense, ExpenseCategory, ExpenseStatus

    result = ImportResult()
    try:
        headers, rows = parse_csv_upload(request.FILES.get('csv_file'))
    except ValueError as e:
        result.add_error(1, str(e))
        return render(request, 'core/import_summary_modal.html', {
            'result': result,
            'cancel_url': '/core/expenses/',
        })

    for i, row in enumerate(rows, start=2):
        try:
            with transaction.atomic():
                norm = {normalize_header(k): v.strip() for k, v in row.items() if v}

                date_val = safe_date(norm.get('purchase_date', ''))
                if not date_val:
                    result.add_error(i, 'Purchase Date is required or invalid format.', row)
                    result.skipped += 1
                    continue

                amount = safe_decimal(norm.get('total_cost'))
                if amount <= 0:
                    result.add_error(i, 'Total Cost must be greater than 0.', row)
                    result.skipped += 1
                    continue

                # Resolve category
                cat_name = norm.get('category', 'General')
                category = ExpenseCategory.objects.filter(name__iexact=cat_name).first()
                if not category:
                    category = ExpenseCategory.objects.filter(code__iexact=cat_name).first()
                if not category:
                    cat_code = cat_name[:30].upper().replace(' ', '_')
                    try:
                        category, created_cat = ExpenseCategory.objects.get_or_create(
                            code=cat_code,
                            defaults={'name': cat_name},
                        )
                    except IntegrityError:
                        category = ExpenseCategory.objects.filter(code=cat_code).first()
                        created_cat = False
                    if created_cat:
                        result.add_warning(i, f'Created new expense category: {cat_name}')

                # Resolve status
                status_raw = norm.get('status', 'PAID').upper()
                status = ExpenseStatus.PAID
                for choice in ExpenseStatus.choices:
                    if status_raw in (choice[0], choice[1].upper()):
                        status = choice[0]
                        break

                expense = Expense.objects.create(
                    date=date_val,
                    category=category,
                    item_description=norm.get('item_description', ''),
                    amount=amount,
                    status=status,
                    vendor=norm.get('vendor_name', ''),
                    business_address=norm.get('business_address', ''),
                    reference_no=norm.get('reference_no', ''),
                    memo=norm.get('notes', ''),
                    created_by=request.user,
                )
                result.created += 1

        except Exception as e:
            result.add_error(i, str(e), row)
            result.skipped += 1

    return render(request, 'core/import_summary_modal.html', {
        'result': result,
        'cancel_url': '/core/expenses/',
    })


# ═══════════════════════════════════════════════════════════════════════════
# 3. SALES ORDER IMPORT
# ═══════════════════════════════════════════════════════════════════════════

SALES_ORDER_TEMPLATE_COLUMNS = [
    'Billing Date', 'Product / Service Name', 'Item Code (SKU)', 'Quantity',
    'Item Price', 'Discount (%)', 'Total Amount', 'Payment Status',
    'Sales Channel', 'Receipt No', 'Customer Name', 'Business Address', 'Notes',
]

@login_required
def sales_order_import_template(request):
    return generate_csv_template(SALES_ORDER_TEMPLATE_COLUMNS, 'sales_orders_template.csv')


@login_required
def sales_order_import(request):
    if request.method != 'POST':
        return render(request, 'core/import_modal.html', {
            'title': 'Import Sales Orders',
            'import_url': 'sales_order_import',
            'template_url': 'sales_order_import_template',
            'cancel_url': '/sales/orders/',
        })

    from catalog.models import Item, Unit
    from partners.models import Customer
    from warehouses.models import Warehouse
    from sales.models import SalesOrder, SalesOrderLine, PaymentStatus
    from core.models import SalesChannel, DocumentStatus

    result = ImportResult()
    try:
        headers, rows = parse_csv_upload(request.FILES.get('csv_file'))
    except ValueError as e:
        result.add_error(1, str(e))
        return render(request, 'core/import_summary_modal.html', {
            'result': result,
            'cancel_url': '/sales/orders/',
        })

    # Group rows by receipt_no or customer+date to create one SO per group
    groups = {}
    for i, row in enumerate(rows, start=2):
        norm = {normalize_header(k): v.strip() for k, v in row.items() if v}
        receipt = norm.get('receipt_no', '')
        cust = norm.get('customer_name', '')
        date_str = norm.get('billing_date', '')
        key = receipt or f"{cust}_{date_str}_{i}"
        if key not in groups:
            groups[key] = {'meta': norm, 'lines': [], 'row_start': i}
        groups[key]['lines'].append((i, norm))

    default_warehouse = Warehouse.objects.first()
    if not default_warehouse:
        result.add_error(1, 'No warehouse exists. Please create one first.')
        return render(request, 'core/import_summary_modal.html', {
            'result': result,
            'cancel_url': '/sales/orders/',
        })

    for key, group in groups.items():
        meta = group['meta']
        row_start = group['row_start']
        try:
            with transaction.atomic():
                date_val = safe_date(meta.get('billing_date', ''))
                if not date_val:
                    result.add_error(row_start, 'Billing Date is required or invalid.', meta)
                    result.skipped += len(group['lines'])
                    continue

                # Resolve customer
                cust_name = meta.get('customer_name', 'Walk-in')
                customer = Customer.objects.filter(name__iexact=cust_name).first()
                if not customer:
                    cust_code = cust_name[:30].upper().replace(' ', '-')
                    customer, _ = Customer.objects.get_or_create(
                        code=cust_code,
                        defaults={'name': cust_name, 'address': meta.get('business_address', '')}
                    )
                    result.add_warning(row_start, f'Created new customer: {cust_name}')

                # Resolve payment status
                ps_raw = meta.get('payment_status', 'UNPAID').upper()
                payment_status = PaymentStatus.UNPAID
                for choice in PaymentStatus.choices:
                    if ps_raw in (choice[0], choice[1].upper()):
                        payment_status = choice[0]
                        break

                # Resolve sales channel
                channel_name = meta.get('sales_channel', '')
                channel = None
                if channel_name:
                    channel = SalesChannel.objects.filter(name__iexact=channel_name).first()
                    if not channel:
                        ch_code = channel_name[:30].upper().replace(' ', '_')
                        try:
                            channel, created_ch = SalesChannel.objects.get_or_create(
                                code=ch_code,
                                defaults={'name': channel_name},
                            )
                        except IntegrityError:
                            channel = SalesChannel.objects.filter(code=ch_code).first()
                            created_ch = False
                        if created_ch:
                            result.add_warning(row_start, f'Created new sales channel: {channel_name}')

                # Generate document number
                from django.utils.timezone import now
                ts = now().strftime('%Y%m%d%H%M%S')
                import random
                doc_num = f"SO-IMP-{ts}-{random.randint(1000,9999)}"

                so = SalesOrder.objects.create(
                    document_number=doc_num,
                    customer=customer,
                    warehouse=default_warehouse,
                    order_date=date_val,
                    payment_status=payment_status,
                    sales_channel=channel,
                    receipt_no=meta.get('receipt_no', ''),
                    shipping_address=meta.get('business_address', ''),
                    notes=meta.get('notes', ''),
                    status=DocumentStatus.DRAFT,
                    created_by=request.user,
                )

                for line_i, line_norm in group['lines']:
                    item_code = line_norm.get('item_code_sku', '')
                    item_name = line_norm.get('product___service_name', '')

                    item = None
                    if item_code:
                        item = Item.objects.filter(code__iexact=item_code).first()
                    if not item and item_name:
                        item = Item.objects.filter(name__iexact=item_name).first()
                    if not item:
                        result.add_error(line_i, f'Item not found: {item_code or item_name}. Skipping line.', line_norm)
                        continue

                    qty = safe_decimal(line_norm.get('quantity', '1'))
                    price = safe_decimal(line_norm.get('item_price'))
                    if price <= 0:
                        price = item.selling_price
                    discount_pct = safe_decimal(line_norm.get('discount_pct', '0'))

                    SalesOrderLine.objects.create(
                        sales_order=so,
                        item=item,
                        qty_ordered=qty,
                        unit=item.stock_unit,
                        unit_price=price,
                        discount_pct=discount_pct,
                        notes=line_norm.get('notes', ''),
                    )

                result.created += 1

        except Exception as e:
            result.add_error(row_start, str(e), meta)
            result.skipped += 1

    return render(request, 'core/import_summary_modal.html', {
        'result': result,
        'cancel_url': '/sales/orders/',
    })


# ═══════════════════════════════════════════════════════════════════════════
# 4. SUPPLY ITEMS IMPORT
# ═══════════════════════════════════════════════════════════════════════════

SUPPLY_TEMPLATE_COLUMNS = [
    'Product Name', 'Item Code', 'Supplier/Brand', 'Category',
    'Units per Piece', 'Units', 'Item Cost',
    'Available Stocks', 'Low Stock Alert Level', 'Minimum Stock',
    'Status', 'Notes',
]

@login_required
def supply_import_template(request):
    return generate_csv_template(SUPPLY_TEMPLATE_COLUMNS, 'supply_items_template.csv')


@login_required
def supply_import(request):
    if request.method != 'POST':
        return render(request, 'core/import_modal.html', {
            'title': 'Import Supply Items',
            'import_url': 'supply_import',
            'template_url': 'supply_import_template',
            'cancel_url': '/supplies/',
        })

    from core.models import SupplyItem, SupplyCategory

    result = ImportResult()
    try:
        headers, rows = parse_csv_upload(request.FILES.get('csv_file'))
    except ValueError as e:
        result.add_error(1, str(e))
        return render(request, 'core/import_summary_modal.html', {
            'result': result,
            'cancel_url': '/supplies/',
        })

    for i, row in enumerate(rows, start=2):
        try:
            with transaction.atomic():
                norm = {normalize_header(k): v.strip() for k, v in row.items() if v}

                name = norm.get('product_name', '').strip()
                code = norm.get('item_code', '').strip()
                if not code and not name:
                    result.skipped += 1
                    continue
                if not code:
                    code = name[:50].upper().replace(' ', '-')

                # Resolve category
                cat_name = norm.get('category', '')
                category = None
                if cat_name:
                    category = SupplyCategory.objects.filter(name__iexact=cat_name).first()
                    if not category:
                        cat_code = cat_name[:30].upper().replace(' ', '_')
                        try:
                            category, created_cat = SupplyCategory.objects.get_or_create(
                                code=cat_code,
                                defaults={'name': cat_name},
                            )
                        except IntegrityError:
                            category = SupplyCategory.objects.filter(code=cat_code).first()
                            created_cat = False
                        if created_cat:
                            result.add_warning(i, f'Created new supply category: {cat_name}')

                defaults = {
                    'name': name or code,
                    'category': category,
                    'supplier_brand': norm.get('supplier_brand', norm.get('supplier', '')),
                    'units_per_piece': safe_decimal(norm.get('units_per_piece', '1'), Decimal('1')),
                    'unit': norm.get('units', 'pcs'),
                    'cost_per_unit': safe_decimal(norm.get('item_cost')),
                    'current_stock': safe_decimal(norm.get('available_stocks')),
                    'low_stock_alert_level': safe_decimal(norm.get('low_stock_alert_level')),
                    'minimum_stock': safe_decimal(norm.get('minimum_stock')),
                    'notes': norm.get('notes', ''),
                }

                obj, created = SupplyItem.objects.update_or_create(
                    code=code, defaults=defaults
                )
                if created:
                    result.created += 1
                else:
                    result.updated += 1

        except Exception as e:
            result.add_error(i, str(e), row)
            result.skipped += 1

    return render(request, 'core/import_summary_modal.html', {
        'result': result,
        'cancel_url': '/supplies/',
    })


# ═══════════════════════════════════════════════════════════════════════════
# 5. PROCUREMENT / STOCK-IN IMPORT
# Creates a GoodsReceipt (GRN) per date+warehouse+supplier group then posts
# it via inventory.services.post_goods_receipt() to add stock to inventory.
# ═══════════════════════════════════════════════════════════════════════════

PROCUREMENT_TEMPLATE_COLUMNS = [
    'Stock-In Date', 'Warehouse', 'Supplier', 'Product Name', 'Item Code',
    'Qty', 'Unit', 'Unit Cost', 'Location', 'Notes',
]


@login_required
def procurement_import_template(request):
    return generate_csv_template(PROCUREMENT_TEMPLATE_COLUMNS, 'procurement_stockin_template.csv')


@login_required
def procurement_import(request):
    if request.method != 'POST':
        return render(request, 'core/import_modal.html', {
            'title': 'Import Stock-In (Procurement)',
            'import_url': 'procurement_import',
            'template_url': 'procurement_import_template',
            'cancel_url': '/procurement/goods-receipts/',
        })

    from catalog.models import Item, Unit as CatalogUnit
    from procurement.models import GoodsReceipt, GoodsReceiptLine
    from partners.models import Supplier
    from warehouses.models import Warehouse, Location
    from inventory.services import post_goods_receipt, generate_document_number

    result = ImportResult()
    try:
        headers, rows = parse_csv_upload(request.FILES.get('csv_file'))
    except ValueError as e:
        result.add_error(1, str(e))
        return render(request, 'core/import_summary_modal.html', {
            'result': result,
            'cancel_url': '/procurement/goods-receipts/',
        })

    # Resolve defaults (first active warehouse / first supplier) used as fallback
    default_warehouse = Warehouse.objects.first()
    default_supplier = Supplier.objects.first()

    # Group rows into GRN batches: one GRN per (date, warehouse, supplier)
    # We process each row individually but group them into GRNs
    from collections import defaultdict
    grn_groups = defaultdict(list)  # key -> list of (i, norm, row)

    for i, row in enumerate(rows, start=2):
        norm = {normalize_header(k): v.strip() for k, v in row.items() if v}
        date_val = safe_date(norm.get('stock-in_date', norm.get('stockin_date', norm.get('stock_in_date', ''))))
        if not date_val:
            result.add_error(i, 'Stock-In Date is required or invalid format.', row)
            result.skipped += 1
            continue

        # Resolve warehouse
        wh_val = norm.get('warehouse', '').strip()
        warehouse = None
        if wh_val:
            warehouse = Warehouse.objects.filter(code__iexact=wh_val).first() or \
                        Warehouse.objects.filter(name__iexact=wh_val).first()
        if not warehouse:
            warehouse = default_warehouse
        if not warehouse:
            result.add_error(i, 'No warehouse found and no default warehouse exists.', row)
            result.skipped += 1
            continue

        # Resolve supplier
        sup_val = norm.get('supplier', '').strip()
        supplier = None
        if sup_val:
            supplier = Supplier.objects.filter(name__iexact=sup_val).first() or \
                       Supplier.objects.filter(code__iexact=sup_val).first()
        if not supplier:
            supplier = default_supplier
        if not supplier:
            result.add_error(i, 'No supplier found and no default supplier exists.', row)
            result.skipped += 1
            continue

        grn_key = (date_val, warehouse.pk, supplier.pk)
        grn_groups[grn_key].append((i, norm, row, warehouse, supplier, date_val))

    # Process each GRN group
    for grn_key, line_entries in grn_groups.items():
        date_val, wh_pk, sup_pk = grn_key
        warehouse = line_entries[0][3]
        supplier = line_entries[0][4]

        try:
            with transaction.atomic():
                # Get default location for this warehouse
                default_location = Location.objects.filter(
                    warehouse=warehouse, is_active=True
                ).first()

                # Build GRN lines first; validate all before creating GRN
                grn_lines_data = []
                for (i, norm, row, _wh, _sup, _dt) in line_entries:
                    item_name = norm.get('product_name', '').strip()
                    item_code = norm.get('item_code', '').strip()

                    # Resolve catalog item — name first, code fallback, partial fallback
                    catalog_item = None
                    suggestion = None
                    if item_name:
                        catalog_item = Item.objects.filter(name__iexact=item_name).first()
                    if not catalog_item and item_code:
                        catalog_item = Item.objects.filter(code__iexact=item_code).first()
                    if not catalog_item and item_name:
                        partial_qs = Item.objects.filter(name__icontains=item_name)
                        if partial_qs.count() == 1:
                            catalog_item = partial_qs.first()
                        elif partial_qs.exists():
                            suggestion = ', '.join(partial_qs.values_list('name', flat=True)[:5])

                    if not catalog_item:
                        tried = []
                        if item_name:
                            tried.append(f'name "{item_name}"')
                        if item_code:
                            tried.append(f'code "{item_code}"')
                        tried_str = ' and '.join(tried) if tried else '(no name or code provided)'
                        msg = f'Item not found by {tried_str}.'
                        if suggestion:
                            msg += f' Close matches: {suggestion}'
                        result.add_error(i, msg, row)
                        result.skipped += 1
                        continue

                    qty = safe_decimal(norm.get('qty', norm.get('stocks_added', '0')))
                    if qty <= 0:
                        result.add_error(i, 'Qty must be greater than 0.', row)
                        result.skipped += 1
                        continue

                    # Resolve unit
                    unit_val = norm.get('unit', '').strip()
                    unit = None
                    if unit_val:
                        unit = CatalogUnit.objects.filter(abbreviation__iexact=unit_val).first() or \
                               CatalogUnit.objects.filter(name__iexact=unit_val).first()
                    if not unit:
                        unit = catalog_item.stock_unit

                    # Resolve location
                    loc_val = norm.get('location', '').strip()
                    location = None
                    if loc_val:
                        location = Location.objects.filter(
                            warehouse=warehouse, code__iexact=loc_val
                        ).first()
                    if not location:
                        location = default_location
                    if not location:
                        result.add_error(i, f'No location found for warehouse "{warehouse.code}".', row)
                        result.skipped += 1
                        continue

                    unit_cost = safe_decimal(norm.get('unit_cost', '0'))

                    grn_lines_data.append({
                        'item': catalog_item,
                        'location': location,
                        'qty': qty,
                        'unit': unit,
                        'unit_cost': unit_cost,
                        'notes': norm.get('notes', ''),
                        'row_num': i,
                    })

                if not grn_lines_data:
                    continue

                # Create GRN header
                grn = GoodsReceipt.objects.create(
                    document_number=generate_document_number('GRN', GoodsReceipt),
                    purchase_order=None,
                    supplier=supplier,
                    warehouse=warehouse,
                    receipt_date=date_val,
                    notes=f'Imported via CSV on {date_val}',
                    created_by=request.user,
                )

                # Create GRN lines
                for line_data in grn_lines_data:
                    GoodsReceiptLine.objects.create(
                        goods_receipt=grn,
                        item=line_data['item'],
                        location=line_data['location'],
                        qty=line_data['qty'],
                        unit=line_data['unit'],
                        notes=line_data['notes'],
                    )

                # Post the GRN — creates StockMoves and updates StockBalances
                post_goods_receipt(grn, request.user)
                result.created += len(grn_lines_data)

        except Exception as e:
            for (i, norm, row, _wh, _sup, _dt) in line_entries:
                result.add_error(i, f'GRN creation/posting failed: {e}', row)
                result.skipped += 1

    return render(request, 'core/import_summary_modal.html', {
        'result': result,
        'cancel_url': '/procurement/goods-receipts/',
    })


# ═══════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _flash_import_result(request, result, label):
    """Flash a single consolidated message from an ImportResult."""
    parts = []
    if result.success_count > 0:
        summary = f'{label} import complete: {result.created} created'
        if result.updated:
            summary += f', {result.updated} updated'
        if result.skipped:
            summary += f', {result.skipped} skipped'
        parts.append(summary)
    elif result.skipped > 0:
        parts.append(f'{label} import: {result.skipped} rows skipped. Check your data.')
    else:
        parts.append(f'{label} import: no rows processed.')

    # Append detail lines
    details = []
    for w in result.warnings[:5]:
        details.append(w)
    for e in result.errors[:5]:
        details.append(e)
    remaining = len(result.errors) - 5
    if remaining > 0:
        details.append(f'... and {remaining} more errors.')

    if details:
        parts.append('Details: ' + ' | '.join(details))

    msg = ' '.join(parts)
    if result.success_count > 0:
        messages.success(request, msg)
    elif result.errors:
        messages.error(request, msg)
    else:
        messages.warning(request, msg)
