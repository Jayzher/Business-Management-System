# Item Detail - Stock Movements Pagination Fix

## Overview
Updated the Item Detail page to show **all stock movements** with pagination instead of just the recent 20 movements, sorted by most recent first.

## Problem

### Before:
- Only showed the **first 20 movements** (limited by `[:20]`)
- No pagination - couldn't see older movements
- Title said "Recent Stock Movements" but didn't clarify the limit
- No sorting specified (relied on database default order)
- Users couldn't view complete movement history

## Solution

### Changes Made:

#### 1. **Updated View** (`catalog/views.py`)

**Before:**
```python
recent_moves = StockMove.objects.filter(
    item=item, status='POSTED'
).select_related('unit', 'from_location', 'to_location', 'created_by')[:20]

return render(request, 'catalog/item_detail.html', {
    ...
    'recent_moves': recent_moves,
})
```

**After:**
```python
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Stock movements with pagination - sorted by most recent first
moves_list = StockMove.objects.filter(
    item=item, status='POSTED'
).select_related(
    'unit', 'from_location', 'to_location', 'created_by'
).order_by('-posted_at', '-created_at', '-id')  # Most recent first

# Pagination
page = request.GET.get('page', 1)
paginator = Paginator(moves_list, 25)  # 25 movements per page

try:
    moves = paginator.page(page)
except PageNotAnInteger:
    moves = paginator.page(1)
except EmptyPage:
    moves = paginator.page(paginator.num_pages)

return render(request, 'catalog/item_detail.html', {
    ...
    'moves': moves,  # Changed from recent_moves to moves (paginated)
})
```

**Key Changes:**
- ✅ Removed `[:20]` limit - now shows ALL movements
- ✅ Added explicit sorting: `-posted_at`, `-created_at`, `-id` (most recent first)
- ✅ Added pagination with 25 items per page
- ✅ Proper error handling for invalid page numbers
- ✅ Changed context variable from `recent_moves` to `moves`

#### 2. **Updated Template** (`templates/catalog/item_detail.html`)

**Before:**
```html
<!-- Recent Stock Movements -->
<div class="card card-outline card-secondary">
  <div class="card-header">
    <h3 class="card-title">
      <i class="fas fa-exchange-alt mr-1"></i> Recent Stock Movements
    </h3>
  </div>
  <div class="card-body table-responsive p-0">
    <table class="table table-hover text-nowrap mb-0">
      ...
      {% for move in recent_moves %}
      ...
      {% endfor %}
    </table>
  </div>
</div>
```

**After:**
```html
<!-- Stock Movements (All with Pagination) -->
<div class="card card-outline card-secondary">
  <div class="card-header">
    <h3 class="card-title">
      <i class="fas fa-exchange-alt mr-1"></i> Stock Movements
    </h3>
    <div class="card-tools">
      <span class="badge badge-secondary">
        {{ moves.paginator.count }} total movement{{ moves.paginator.count|pluralize }}
      </span>
    </div>
  </div>
  <div class="card-body table-responsive p-0">
    <table class="table table-hover text-nowrap mb-0">
      ...
      {% for move in moves %}
      ...
      {% endfor %}
    </table>
  </div>
  {% if moves.has_other_pages %}
  <div class="card-footer clearfix">
    <ul class="pagination pagination-sm m-0 float-right">
      <!-- Pagination controls -->
    </ul>
    <div class="float-left mt-2">
      <small class="text-muted">
        Showing {{ moves.start_index }} to {{ moves.end_index }} 
        of {{ moves.paginator.count }} movement{{ moves.paginator.count|pluralize }}
      </small>
    </div>
  </div>
  {% endif %}
</div>
```

**Key Changes:**
- ✅ Changed title from "Recent Stock Movements" to "Stock Movements"
- ✅ Added badge showing total count of movements
- ✅ Changed loop variable from `recent_moves` to `moves`
- ✅ Added pagination controls in card footer
- ✅ Added "Showing X to Y of Z" indicator

## Features

### 1. **Complete Movement History**
- Shows **all** stock movements for the item
- No arbitrary limit
- Full audit trail available

### 2. **Sorted by Most Recent**
Sorting order:
1. `posted_at` (descending) - when the movement was posted
2. `created_at` (descending) - when the record was created
3. `id` (descending) - unique identifier as tiebreaker

**Result**: Most recent movements appear first

### 3. **Pagination Controls**

```
┌─────────────────────────────────────────────────────────┐
│ Stock Movements                    [125 total movements]│
├─────────────────────────────────────────────────────────┤
│ [Movement table with 25 rows]                          │
├─────────────────────────────────────────────────────────┤
│ Showing 1 to 25 of 125 movements                       │
│                    [« First] [Previous] [Page 1 of 5]  │
│                    [Next] [Last »]                      │
└─────────────────────────────────────────────────────────┘
```

**Pagination Features:**
- First / Previous / Next / Last buttons
- Current page indicator (e.g., "Page 1 of 5")
- Shows range (e.g., "Showing 1 to 25 of 125")
- Disabled state for unavailable actions
- 25 movements per page

### 4. **Total Count Badge**
- Shows total number of movements in header
- Updates dynamically based on actual count
- Pluralization handled automatically

## User Experience

### Before:
```
User: "I need to see all movements for this item"
System: Shows only 20 movements
User: "Where are the rest? I can't see older movements!"
```

### After:
```
User: "I need to see all movements for this item"
System: Shows 25 movements with pagination
User: "Great! I can see there are 125 total movements"
User: Clicks "Next" to see more
System: Shows movements 26-50
User: "Perfect! I can navigate through all movements"
```

## Pagination Details

### Page Size
- **25 movements per page** (configurable in view)
- Good balance between:
  - Loading performance
  - User convenience
  - Screen real estate

### URL Parameters
- Uses `?page=N` query parameter
- Examples:
  - `/catalog/item/123/` - Page 1 (default)
  - `/catalog/item/123/?page=2` - Page 2
  - `/catalog/item/123/?page=5` - Page 5

### Error Handling
```python
try:
    moves = paginator.page(page)
except PageNotAnInteger:
    moves = paginator.page(1)  # Show first page
except EmptyPage:
    moves = paginator.page(paginator.num_pages)  # Show last page
```

**Handles:**
- Invalid page numbers (e.g., `?page=abc`) → Shows page 1
- Out of range (e.g., `?page=999`) → Shows last page
- Negative numbers → Shows page 1

## Performance Considerations

### Query Optimization
```python
.select_related('unit', 'from_location', 'to_location', 'created_by')
```

**Benefits:**
- Reduces database queries (N+1 problem avoided)
- Fetches related objects in single query
- Faster page load times

### Pagination Benefits
- Only loads 25 records at a time (not all movements)
- Reduces memory usage
- Faster rendering
- Better for items with thousands of movements

### Sorting Performance
```python
.order_by('-posted_at', '-created_at', '-id')
```

**Considerations:**
- Uses database indexes for efficient sorting
- `posted_at` should be indexed for best performance
- Multiple sort fields ensure consistent ordering

## Testing Checklist

- [ ] View item with no movements (shows empty state)
- [ ] View item with < 25 movements (no pagination shown)
- [ ] View item with > 25 movements (pagination appears)
- [ ] Click "Next" button (shows next page)
- [ ] Click "Previous" button (shows previous page)
- [ ] Click "First" button (goes to page 1)
- [ ] Click "Last" button (goes to last page)
- [ ] Try invalid page number `?page=abc` (shows page 1)
- [ ] Try out of range `?page=999` (shows last page)
- [ ] Verify movements are sorted by most recent first
- [ ] Check total count badge shows correct number
- [ ] Verify "Showing X to Y of Z" is accurate

## Example Scenarios

### Scenario 1: Item with 3 Movements
```
Stock Movements                    [3 total movements]
┌────────────────────────────────────────────────────┐
│ Date       │ Type    │ Qty  │ From │ To │ Ref    │
├────────────────────────────────────────────────────┤
│ Jan 15 10:30│ RECEIVE │ 100 │  -   │ A1 │ GRN-001│
│ Jan 14 14:20│ DELIVER │  50 │ A1   │  - │ DN-001 │
│ Jan 13 09:15│ ADJUST  │  10 │  -   │ A1 │ ADJ-001│
└────────────────────────────────────────────────────┘
(No pagination - all movements fit on one page)
```

### Scenario 2: Item with 125 Movements
```
Stock Movements                    [125 total movements]
┌────────────────────────────────────────────────────┐
│ [25 most recent movements shown]                  │
└────────────────────────────────────────────────────┘
Showing 1 to 25 of 125 movements
[« First] [Previous] [Page 1 of 5] [Next] [Last »]
```

### Scenario 3: Navigating to Page 3
```
Stock Movements                    [125 total movements]
┌────────────────────────────────────────────────────┐
│ [Movements 51-75 shown]                           │
└────────────────────────────────────────────────────┘
Showing 51 to 75 of 125 movements
[« First] [Previous] [Page 3 of 5] [Next] [Last »]
```

## Benefits

### 1. **Complete Audit Trail**
- Users can see ALL movements, not just recent 20
- Important for compliance and auditing
- Historical data is accessible

### 2. **Better User Experience**
- Clear indication of total movements
- Easy navigation through pages
- No confusion about missing data

### 3. **Performance**
- Pagination prevents loading thousands of records at once
- Faster page loads
- Better database performance

### 4. **Scalability**
- Works well with items that have many movements
- No performance degradation with large datasets
- Consistent experience regardless of movement count

## Summary

The Item Detail page now shows **all stock movements** with proper pagination and sorting:

✅ **All movements** displayed (not just 20)  
✅ **Sorted by most recent** first  
✅ **25 movements per page** (configurable)  
✅ **Full pagination controls** (First, Previous, Next, Last)  
✅ **Total count badge** in header  
✅ **Range indicator** (Showing X to Y of Z)  
✅ **Error handling** for invalid pages  
✅ **Optimized queries** with select_related  

Users can now view the complete movement history for any item with easy navigation!
