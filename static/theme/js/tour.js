/**
 * WIS Tour Guide System
 * ─────────────────────
 * Interactive walkthrough for new users using Driver.js.
 * Supports: full tour, per-section tours, replay, skip, localStorage state.
 */
(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════════════════════
   * CONFIGURATION
   * ═══════════════════════════════════════════════════════════════════════ */
  const TOUR_VERSION = '1.0';
  const LS_KEY_FULL = 'wis_tour_completed_' + TOUR_VERSION;
  const LS_KEY_SECTION = 'wis_section_tours_' + TOUR_VERSION;

  /* ═══════════════════════════════════════════════════════════════════════
   * HELPERS
   * ═══════════════════════════════════════════════════════════════════════ */
  function el(selector) { return document.querySelector(selector); }
  function elAll(selector) { return document.querySelectorAll(selector); }
  function exists(selector) { return !!el(selector); }

  function markFullTourDone() {
    try { localStorage.setItem(LS_KEY_FULL, 'true'); } catch (e) { /* private browsing */ }
  }
  function isFullTourDone() {
    try { return localStorage.getItem(LS_KEY_FULL) === 'true'; } catch (e) { return true; }
  }
  function resetFullTour() {
    try { localStorage.removeItem(LS_KEY_FULL); } catch (e) { /* ok */ }
  }

  /* ═══════════════════════════════════════════════════════════════════════
   * FULL SYSTEM TOUR  (Dashboard page)
   * Covers: navigation, KPIs, charts, quick actions, sidebar modules
   * ═══════════════════════════════════════════════════════════════════════ */
  function buildFullTourSteps() {
    var steps = [];

    // ── Welcome ───────────────────────────────────────────────────────
    steps.push({
      popover: {
        title: '👋 Welcome to WIS!',
        description: '<p>Welcome to the <strong>Warehouse Inventory System</strong> — your all-in-one business management tool.</p>' +
          '<p>This guided tour will walk you through every feature so you can get started quickly.</p>' +
          '<p class="mb-0"><small class="text-muted">You can <strong>skip</strong> anytime or <strong>replay</strong> this tour later from the help button in the top bar.</small></p>',
        position: 'center',
      }
    });

    // ── Sidebar ───────────────────────────────────────────────────────
    if (exists('.main-sidebar')) {
      steps.push({
        element: '.main-sidebar',
        popover: {
          title: '📌 Sidebar Navigation',
          description: '<p>This is your <strong>main navigation panel</strong>. All modules are organized into collapsible sections.</p>' +
            '<p>Click any section to expand it and see its sub-pages.</p>' +
            '<p class="mb-0"><small>Tip: Click the ☰ hamburger icon in the top-left to collapse or expand the sidebar.</small></p>',
          position: 'right',
        }
      });
    }

    // ── Navbar ─────────────────────────────────────────────────────────
    if (exists('.main-header')) {
      steps.push({
        element: '.main-header',
        popover: {
          title: '🔝 Top Navigation Bar',
          description: '<p>Quick access to <strong>Home</strong>, your <strong>user profile</strong>, and <strong>fullscreen mode</strong>.</p>' +
            '<p class="mb-0">The <i class="fas fa-question-circle"></i> <strong>Help</strong> button lets you replay this tour anytime.</p>',
          position: 'bottom',
        }
      });
    }

    // ── Period Toggle ─────────────────────────────────────────────────
    if (exists('.period-toggle')) {
      steps.push({
        element: '.period-toggle',
        popover: {
          title: '📅 Period Selector',
          description: '<p>Switch between <strong>Today</strong>, <strong>This Week</strong>, <strong>This Month</strong>, or <strong>This Year</strong> to filter all dashboard data.</p>' +
            '<p class="mb-0">All KPIs, charts, and tables below will update based on your selection.</p>',
          position: 'bottom',
        }
      });
    }

    // ── KPI Row ───────────────────────────────────────────────────────
    if (exists('.kpi-card')) {
      steps.push({
        element: '.kpi-card',
        popover: {
          title: '📊 Key Performance Indicators',
          description: '<p>These cards show your most important business metrics at a glance:</p>' +
            '<ul class="mb-0" style="padding-left:1.2rem;">' +
            '<li><strong>Revenue</strong> — Total sales income</li>' +
            '<li><strong>Sales Count</strong> — Number of transactions</li>' +
            '<li><strong>Gross Profit</strong> — Revenue minus cost of goods</li>' +
            '<li><strong>Expenses</strong> — Total recorded expenses</li>' +
            '<li><strong>Net Profit</strong> — Final profit after all costs</li>' +
            '<li><strong>Inventory Value</strong> — Stock worth at cost price</li></ul>',
          position: 'bottom',
        }
      });
    }

    // ── Small Boxes ───────────────────────────────────────────────────
    if (exists('.small-box')) {
      steps.push({
        element: '.small-box',
        popover: {
          title: '📦 Quick Status Boxes',
          description: '<p>These colored boxes give you instant visibility into:</p>' +
            '<ul class="mb-0" style="padding-left:1.2rem;">' +
            '<li><strong>Active Items</strong> — Products in your catalog</li>' +
            '<li><strong>Low Stock Alerts</strong> — Items below minimum threshold</li>' +
            '<li><strong>Pending GRNs</strong> — Goods receipts awaiting processing</li>' +
            '<li><strong>Pending Deliveries</strong> — Deliveries to ship</li></ul>' +
            '<p class="mt-1 mb-0"><small>Click any box to jump straight to that section.</small></p>',
          position: 'bottom',
        }
      });
    }

    // ── Charts ────────────────────────────────────────────────────────
    if (exists('#revenueChart')) {
      steps.push({
        element: '#revenueChart',
        popover: {
          title: '📈 Revenue Trend Chart',
          description: '<p>Visualize your <strong>daily revenue</strong> over the last 7 days.</p>' +
            '<p class="mb-0">Use this to spot sales trends and patterns in your business.</p>',
          position: 'top',
        }
      });
    }

    // ── Top Items Table ───────────────────────────────────────────────
    if (exists('.fa-trophy')) {
      var topItemCard = el('.fa-trophy');
      if (topItemCard) topItemCard = topItemCard.closest('.card');
      if (topItemCard) {
        steps.push({
          element: topItemCard,
          popover: {
            title: '🏆 Top Selling Items',
            description: '<p>See which products are performing best by <strong>quantity sold</strong> and <strong>revenue generated</strong>.</p>' +
              '<p class="mb-0">Use this data to make restocking and pricing decisions.</p>',
            position: 'top',
          }
        });
      }
    }

    // ── Quick Actions ─────────────────────────────────────────────────
    if (exists('.quick-action')) {
      var qaCard = el('.quick-action');
      if (qaCard) qaCard = qaCard.closest('.card');
      if (qaCard) {
        steps.push({
          element: qaCard,
          popover: {
            title: '⚡ Quick Actions',
            description: '<p>One-click shortcuts to the most common tasks:</p>' +
              '<ul class="mb-0" style="padding-left:1.2rem;">' +
              '<li><strong>POS Shift</strong> — Open a point-of-sale session</li>' +
              '<li><strong>Add Expense</strong> — Record a business expense</li>' +
              '<li><strong>Stock In</strong> — Receive goods into warehouse</li>' +
              '<li><strong>Invoices</strong> — View/generate invoices</li>' +
              '<li><strong>P&L</strong> — Open financial statement</li>' +
              '<li><strong>Supplies</strong> — Manage office/shop supplies</li></ul>',
            position: 'left',
          }
        });
      }
    }

    // ── Business Flow ─────────────────────────────────────────────────
    if (exists('.fa-route')) {
      var flowCard = el('.fa-route');
      if (flowCard) flowCard = flowCard.closest('.card');
      if (flowCard) {
        steps.push({
          element: flowCard,
          popover: {
            title: '🗺️ Business Flow Guide',
            description: '<p>This checklist shows the <strong>recommended order</strong> for setting up and running your business in WIS:</p>' +
              '<ol class="mb-0" style="padding-left:1.2rem;font-size:.85rem;">' +
              '<li>Setup business info & categories</li>' +
              '<li>List products/services</li>' +
              '<li>Stock in via Purchase Orders</li>' +
              '<li>Sell via POS or Sales Orders</li>' +
              '<li>Generate invoices</li>' +
              '<li>Record expenses</li>' +
              '<li>Review reports & set goals</li></ol>',
            position: 'left',
          }
        });
      }
    }

    // ── SIDEBAR MODULE TOURS ──────────────────────────────────────────
    var sidebarModules = [
      {
        selector: '[data-tour-id="nav-catalog"]',
        title: '📦 Catalog Module',
        desc: '<p>Manage your <strong>product and service listings</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Items</strong> — Add products with SKU, price, cost, images</li>' +
          '<li><strong>Categories</strong> — Organize items into groups</li>' +
          '<li><strong>Units</strong> — Define units of measure (pcs, kg, liters, etc.)</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-partners"]',
        title: '🤝 Partners Module',
        desc: '<p>Manage your business contacts:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Suppliers</strong> — Companies you buy from</li>' +
          '<li><strong>Customers</strong> — Companies or people you sell to</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-warehouses"]',
        title: '🏭 Warehouses Module',
        desc: '<p>Define your <strong>physical storage locations</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Warehouses</strong> — Your storage facilities</li>' +
          '<li><strong>Locations</strong> — Specific bins/shelves within warehouses</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-procurement"]',
        title: '🚚 Procurement Module',
        desc: '<p>Handle the <strong>purchasing process</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Purchase Orders</strong> — Create orders to suppliers</li>' +
          '<li><strong>Goods Receipts</strong> — Receive and verify incoming stock</li></ul>' +
          '<p class="mt-1 mb-0"><small>This is how inventory enters your system.</small></p>',
      },
      {
        selector: '[data-tour-id="nav-sales"]',
        title: '🛒 Sales Module',
        desc: '<p>Manage your <strong>revenue operations</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Sales Orders</strong> — Formal customer orders</li>' +
          '<li><strong>Deliveries</strong> — Ship goods to customers</li>' +
          '<li><strong>Invoices</strong> — Generate professional invoices</li>' +
          '<li><strong>Sales Channels</strong> — Track where sales come from (Store, Online, etc.)</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-expenses"]',
        title: '🧾 Expenses Module',
        desc: '<p>Track all <strong>business expenses</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Expense Listing</strong> — Record rent, utilities, salaries, supplies, etc.</li>' +
          '<li><strong>Expense Categories</strong> — Organize expenses; mark categories as COGS or OPEX</li></ul>' +
          '<p class="mt-1 mb-0"><small>COGS categories affect Cost of Goods Sold in your P&L statement.</small></p>',
      },
      {
        selector: '[data-tour-id="nav-supplies"]',
        title: '📋 Supplies Module',
        desc: '<p>Track <strong>consumable supplies</strong> (office supplies, cleaning materials, etc.):</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Supply Items</strong> — List supplies with stock levels</li>' +
          '<li><strong>Movements</strong> — Record stock-in and stock-out</li>' +
          '<li><strong>Supply Categories</strong> — Organize supply items</li></ul>' +
          '<p class="mt-1 mb-0"><small>Low stock alerts appear when levels drop below minimum.</small></p>',
      },
      {
        selector: '[data-tour-id="nav-inventory"]',
        title: '🔄 Inventory Module',
        desc: '<p>Manage <strong>stock movements and adjustments</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Stock Movements</strong> — View all inventory transactions</li>' +
          '<li><strong>Transfers</strong> — Move stock between warehouses</li>' +
          '<li><strong>Adjustments</strong> — Correct stock counts</li>' +
          '<li><strong>Damaged Stock</strong> — Record damaged/lost items</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-pos"]',
        title: '💳 POS (Point of Sale)',
        desc: '<p>Run your <strong>retail sales terminal</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Registers</strong> — Setup POS terminals</li>' +
          '<li><strong>Open Shift</strong> — Start a new cashier session</li>' +
          '<li><strong>Shifts</strong> — View shift history & summaries</li>' +
          '<li><strong>Receipts</strong> — Browse past sale receipts</li></ul>' +
          '<p class="mt-1 mb-0"><small>Each sale automatically deducts inventory and can generate an invoice.</small></p>',
      },
      {
        selector: '[data-tour-id="nav-pricing"]',
        title: '🏷️ Pricing Module',
        desc: '<p>Control your <strong>pricing strategies</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Price Lists</strong> — Different price tiers (retail, wholesale, VIP)</li>' +
          '<li><strong>Discount Rules</strong> — Automated discounts by quantity, date, or customer</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-qr"]',
        title: '📱 QR Codes Module',
        desc: '<p>Generate and manage <strong>QR code labels</strong> for your items:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>QR Tags</strong> — Generate unique QR codes per item</li>' +
          '<li><strong>Scan</strong> — Use camera to scan and find items instantly</li>' +
          '<li><strong>Print Labels</strong> — Print QR labels for shelving</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-reports"]',
        title: '📊 Reports Module',
        desc: '<p>Analyze your business with <strong>powerful reports</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li><strong>Sales Report</strong> — Revenue by date, channel, and product</li>' +
          '<li><strong>Expense Report</strong> — Expense trends by category and period</li>' +
          '<li><strong>Financial Statement</strong> — Full P&L with COGS, OPEX, Net Profit</li>' +
          '<li><strong>Profit Margin</strong> — Item-level profitability analysis</li>' +
          '<li><strong>Stock Reports</strong> — Stock-on-hand and low stock alerts</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-goals"]',
        title: '🎯 Target Goals',
        desc: '<p>Set and track <strong>business goals</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li>Set revenue targets, sales targets, or custom goals</li>' +
          '<li>Assign goals to team members with due dates</li>' +
          '<li>Track progress with visual progress bars</li>' +
          '<li>Overdue goals are highlighted in red</li></ul>',
      },
      {
        selector: '[data-tour-id="nav-settings"]',
        title: '⚙️ Settings',
        desc: '<p>Configure your <strong>business profile</strong>:</p>' +
          '<ul style="padding-left:1.2rem;" class="mb-0">' +
          '<li>Business name, address, phone, TIN</li>' +
          '<li>Logo for invoices and receipts</li>' +
          '<li>Receipt footer text</li>' +
          '<li>Quick links to setup checklist (categories, channels, units)</li></ul>',
      },
    ];

    sidebarModules.forEach(function (mod) {
      if (exists(mod.selector)) {
        steps.push({
          element: mod.selector,
          popover: {
            title: mod.title,
            description: mod.desc,
            position: 'right',
          }
        });
      }
    });

    // ── Closing ───────────────────────────────────────────────────────
    steps.push({
      popover: {
        title: '🎉 Tour Complete!',
        description: '<p>You\'re all set to start using <strong>WIS</strong>!</p>' +
          '<p><strong>Recommended first steps:</strong></p>' +
          '<ol style="padding-left:1.2rem;" class="mb-2">' +
          '<li>Go to <strong>Settings</strong> and fill in your business info</li>' +
          '<li>Create <strong>Categories</strong> and <strong>Units</strong> in Catalog</li>' +
          '<li>Add your <strong>Products</strong></li>' +
          '<li>Set up a <strong>Warehouse</strong> and start selling!</li></ol>' +
          '<p class="mb-0"><small>💡 Each page has a <i class="fas fa-question-circle"></i> help button for page-specific guidance. Click the <strong>Help</strong> button in the top bar to replay this tour.</small></p>',
        position: 'center',
      }
    });

    return steps;
  }

  /* ═══════════════════════════════════════════════════════════════════════
   * PAGE-SPECIFIC (SECTION) TOURS
   * Each page can define its own mini-tour via data attributes or known selectors.
   * ═══════════════════════════════════════════════════════════════════════ */
  var pageTours = {
    /* ── Dashboard ────────────────────────────────────────────────────── */
    '/dashboard/': {
      title: 'Dashboard Guide',
      steps: function () {
        var s = [];
        if (exists('.period-toggle')) s.push({ element: '.period-toggle', popover: { title: '📅 Period Filter', description: 'Switch the date range to see data for Today, This Week, This Month, or This Year. All cards and charts update automatically.', position: 'bottom' } });
        if (exists('.kpi-card')) s.push({ element: '.kpi-card', popover: { title: '📊 Financial KPIs', description: 'Your key business numbers: Revenue, Sales Count, Gross Profit (with margin %), Expenses, Net Profit, and Inventory Value.', position: 'bottom' } });
        if (exists('.small-box')) s.push({ element: '.small-box', popover: { title: '📦 Status Boxes', description: 'Quick counts for active items, low stock alerts, pending GRNs, and pending deliveries. Click to navigate.', position: 'bottom' } });
        if (exists('#revenueChart')) s.push({ element: '#revenueChart', popover: { title: '📈 Revenue Chart', description: 'Daily revenue trend for the last 7 days. Spot patterns and seasonality at a glance.', position: 'top' } });
        if (exists('#channelChart')) s.push({ element: '#channelChart', popover: { title: '🥧 Channel Breakdown', description: 'Pie chart showing sales distribution across your sales channels (Store, Online, etc.).', position: 'top' } });
        if (exists('#expenseChart')) s.push({ element: '#expenseChart', popover: { title: '🥧 Expense Categories', description: 'Doughnut chart showing how your expenses are distributed across categories.', position: 'top' } });
        return s;
      }
    },

    /* /catalog/items/ (list, detail, create, edit) — see Detail & Sub-page section below */

    /* ── Catalog: Categories ──────────────────────────────────────────── */
    '/catalog/categories/create/': { title: 'Create Category Guide', steps: function () { return [{ popover: { title: '➕ New Category', description: 'Create a product category to organize your catalog items. Categories help you group similar items together for easier management and reporting.', position: 'center' } }]; } },
    '/catalog/categories/': {
      title: 'Categories Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📂 Product Categories', description: 'Categories organize your catalog items into logical groups (e.g., Electronics, Furniture, Hardware). Each item belongs to one category.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Category List', description: 'Shows each category with its code and name. Use the action buttons to edit or delete categories.', position: 'top' } });
        return s;
      }
    },

    /* ── Catalog: Units ───────────────────────────────────────────────── */
    '/catalog/units/create/': { title: 'Create Unit Guide', steps: function () { return [{ popover: { title: '➕ New Unit of Measure', description: 'Define a unit of measure for your items. Examples: pcs (pieces), kg (kilograms), m (meters), box, roll, etc.', position: 'center' } }]; } },
    '/catalog/units/': {
      title: 'Units Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📏 Units of Measure', description: 'Units define how your items are counted and measured. Every item must be assigned a default unit. Common examples: pcs, kg, liters, boxes.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Unit List', description: 'Shows all defined units with their name and abbreviation. Use the action buttons to edit or delete.', position: 'top' } });
        return s;
      }
    },

    /* ── Partners: Suppliers ──────────────────────────────────────────── */
    '/partners/suppliers/create/': { title: 'New Supplier Guide', steps: function () { return [{ popover: { title: '➕ Add Supplier', description: 'Add a new supplier (vendor) to your system. Fill in their company details, contact person, email, and phone. Suppliers are linked to your Purchase Orders.', position: 'center' } }]; } },
    '/partners/suppliers/': {
      title: 'Suppliers Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🤝 Supplier Directory', description: 'Manage all your suppliers (vendors) — companies you purchase goods and materials from. Each supplier can be linked to Purchase Orders and Goods Receipts.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Supplier List', description: 'Shows supplier code, name, contact person, phone, and email. Use the action buttons to edit or delete supplier records.', position: 'top' } });
        return s;
      }
    },

    /* ── Partners: Customers ──────────────────────────────────────────── */
    '/partners/customers/create/': { title: 'New Customer Guide', steps: function () { return [{ popover: { title: '➕ Add Customer', description: 'Add a new customer to your system. Fill in their company name, contact person, and details. Customers are linked to Sales Orders and Invoices.', position: 'center' } }]; } },
    '/partners/customers/': {
      title: 'Customers Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '👥 Customer Directory', description: 'Manage all your customers — companies or individuals you sell to. Customers can be linked to Sales Orders, Delivery Notes, and Invoices.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Customer List', description: 'Shows customer code, name, contact person, phone, and email. Use the action buttons to edit or delete customer records.', position: 'top' } });
        return s;
      }
    },

    /* ── Warehouses ───────────────────────────────────────────────────── */
    '/warehouses/locations/create/': { title: 'New Location Guide', steps: function () { return [{ popover: { title: '➕ Add Location', description: 'Create a storage location (bin, shelf, zone) within a warehouse. Items are stored and tracked at the location level for precise inventory management.', position: 'center' } }]; } },
    '/warehouses/locations/': {
      title: 'Locations Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📍 Warehouse Locations', description: 'Locations are specific storage spots within your warehouses — bins, shelves, zones, or racks. Stock balances are tracked per item per location.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Location List', description: 'Shows each location with its code, name, warehouse, and type (Bin, Shelf, Zone, etc.). Click edit to modify or delete to remove.', position: 'top' } });
        return s;
      }
    },
    /* /warehouses/ and /warehouses/create/ — see Detail & Sub-page section below */

    /* ── Procurement, Sales, Inventory — see Detail & Sub-page section below ── */

    /* ── Inventory: Stock Moves ───────────────────────────────────────── */
    '/inventory/moves/': {
      title: 'Stock Movements Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🔄 Stock Movement History', description: 'A complete audit trail of all inventory movements — every goods receipt, delivery, transfer, adjustment, POS sale, and damaged stock entry is logged here.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Movement Log', description: 'Each row shows the item, quantity, move type (GR_IN, DELIVERY_OUT, TRANSFER, ADJUST, etc.), source/destination location, and who created it.', position: 'top' } });
        return s;
      }
    },

    /* ── Inventory: Transfers ─────────────────────────────────────────── */
    '/inventory/transfers/create/': {
      title: 'Create Transfer Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '➕ New Stock Transfer', description: 'Move inventory between warehouses or between locations within the same warehouse. Select source and destination, then add items with quantities to transfer.', position: 'center' } });
        return s;
      }
    },
    '/inventory/transfers/': {
      title: 'Stock Transfers Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🔄 Stock Transfers', description: 'Transfer inventory between warehouses or locations. <strong>Posting a transfer</strong> decreases stock at the source and increases it at the destination.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Transfer List', description: 'Shows transfer number, source → destination, status, and date. Only DRAFT transfers can be edited.', position: 'top' } });
        return s;
      }
    },

    /* ── Inventory: Adjustments ───────────────────────────────────────── */
    '/inventory/adjustments/create/': { title: 'Create Adjustment Guide', steps: function () { return [{ popover: { title: '➕ New Stock Adjustment', description: 'Correct inventory counts after a physical count or audit. Add items with the adjustment quantity (positive to increase, negative to decrease stock).', position: 'center' } }]; } },
    '/inventory/adjustments/': {
      title: 'Stock Adjustments Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📋 Stock Adjustments', description: 'Adjustments correct inventory discrepancies found during physical counts, audits, or reconciliation. <strong>Posting an adjustment</strong> updates the stock balance at the specified location.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Adjustment List', description: 'Shows adjustment number, warehouse, reason, status, and date. Each posted adjustment creates a corresponding stock move record.', position: 'top' } });
        return s;
      }
    },

    /* ── Inventory: Damaged ───────────────────────────────────────────── */
    '/inventory/damaged/create/': { title: 'Report Damaged Stock Guide', steps: function () { return [{ popover: { title: '➕ Report Damaged Stock', description: 'Record items that are damaged, expired, or lost. This removes the quantity from available inventory. Add a reason and reference number for auditing purposes.', position: 'center' } }]; } },
    '/inventory/damaged/': {
      title: 'Damaged Stock Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '⚠️ Damaged Stock Reports', description: 'Track inventory losses due to damage, expiration, theft, or other causes. <strong>Posting a damage report</strong> reduces stock balance and creates a permanent audit record.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Damage Report List', description: 'Shows report number, warehouse, reason for damage, status, and date. Each report details the affected items and quantities.', position: 'top' } });
        return s;
      }
    },

    /* ── POS: Registers ──────────────────────────────────────────────── */
    '/pos/registers/create/': { title: 'New Register Guide', steps: function () { return [{ popover: { title: '➕ Add POS Register', description: 'Create a new POS terminal. Assign it a name and link it to a warehouse and default location. You\'ll need at least one register before opening a shift.', position: 'center' } }]; } },
    '/pos/registers/': {
      title: 'POS Registers Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '💻 POS Registers', description: 'Registers represent your physical point-of-sale terminals or checkout counters. Each register is linked to a warehouse for stock deduction during sales.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Register List', description: 'Shows register name, linked warehouse, and default location. You can edit or delete registers. At least one register is required to start selling.', position: 'top' } });
        return s;
      }
    },

    /* /pos/shifts/ (list, open, summary) — see Detail & Sub-page section below */

    /* ── POS: Terminal ────────────────────────────────────────────────── */
    '/pos/terminal/': {
      title: 'POS Terminal Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '💳 POS Terminal', description: 'This is your sales checkout screen. Add items to the cart by searching or scanning, adjust quantities, apply payments, and complete the sale.', position: 'center' } });
        if (exists('.cart-items, table')) s.push({ element: 'table', popover: { title: '🛒 Shopping Cart', description: 'Shows items added to the current sale. You can adjust quantities or remove items before checkout.', position: 'left' } });
        return s;
      }
    },

    /* /pos/receipts/ (list + detail) — see Detail & Sub-page section below */

    /* ── Pricing: Price Lists ────────────────────────────────────────── */
    '/pricing/price-lists/create/': { title: 'New Price List Guide', steps: function () { return [{ popover: { title: '➕ Create Price List', description: 'Set up a named price tier (e.g., Retail, Wholesale, VIP). Then add items with their specific prices for this tier. Price lists let you offer different prices to different customer groups.', position: 'center' } }]; } },
    '/pricing/price-lists/': {
      title: 'Price Lists Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🏷️ Price Lists', description: 'Price lists let you define multiple pricing tiers for your products (e.g., Retail, Wholesale, VIP, Distributor). Each list can have different prices per item.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Price List Table', description: 'Shows all your price lists with their name, currency, and date range. Click edit to manage the list items and prices.', position: 'top' } });
        return s;
      }
    },

    /* ── Pricing: Discount Rules ─────────────────────────────────────── */
    '/pricing/discount-rules/create/': { title: 'New Discount Rule Guide', steps: function () { return [{ popover: { title: '➕ Create Discount Rule', description: 'Set up automatic discount rules based on quantity thresholds, date ranges, or customer groups. Discounts are applied automatically during POS checkout.', position: 'center' } }]; } },
    '/pricing/discount-rules/': {
      title: 'Discount Rules Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🏷️ Discount Rules', description: 'Automate discounts for your sales. Rules can be based on quantity bought, date range, or customer type. Applied automatically during POS checkout.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Discount Rule List', description: 'Shows all discount rules with their type, value, conditions, and status. Edit or delete rules as needed.', position: 'top' } });
        return s;
      }
    },

    /* ── QR Codes ─────────────────────────────────────────────────────── */
    '/qr/scan/': {
      title: 'QR Scan Guide',
      steps: function () {
        return [{ popover: { title: '📱 QR Code Scanner', description: 'Use your device camera or enter a QR code value to look up item details instantly. Shows item information, stock levels, and location.', position: 'center' } }];
      }
    },
    '/qr/print/': {
      title: 'QR Print Guide',
      steps: function () {
        return [{ popover: { title: '🖨️ Print QR Labels', description: 'Generate and print QR code labels for your items. Select items, choose label size, and print to attach to shelves, bins, or products for easy scanning.', position: 'center' } }];
      }
    },
    '/qr/': {
      title: 'QR Codes Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📱 QR Code Management', description: 'Generate unique QR codes for each item in your catalog. Use these codes for quick scanning, stock checks, and label printing.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 QR Tag List', description: 'Shows all generated QR codes with their linked item, status, and unique ID. You can regenerate or deactivate tags as needed.', position: 'top' } });
        return s;
      }
    },

    /* ── Reports Dashboard ───────────────────────────────────────────── */
    '/reports/stock-on-hand/': {
      title: 'Stock on Hand Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📦 Stock on Hand Report', description: 'View current inventory levels across all warehouses and locations. Shows the quantity available for each item at each location.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Stock Balances', description: 'Lists every item with its current stock quantity, warehouse, and location. Use this to verify physical counts against system records.', position: 'top' } });
        return s;
      }
    },
    '/reports/stock-movement/': {
      title: 'Stock Movement Report Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🔄 Stock Movement Report', description: 'Track all inventory movements over a period. See what came in (receipts), went out (deliveries/sales), and was moved (transfers/adjustments).', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Movement Details', description: 'Each entry shows the item, quantity, move type, date, source and destination locations.', position: 'top' } });
        return s;
      }
    },
    '/reports/low-stock/': {
      title: 'Low Stock Report Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '⚠️ Low Stock Alerts', description: 'Items whose current stock is at or below their reorder point. Use this report to identify which products need to be reordered urgently.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Low Stock Items', description: 'Shows items with current stock level, reorder point, and how far below the threshold they are. Prioritize restocking the most critical items.', position: 'top' } });
        return s;
      }
    },
    '/reports/profit-margin/': {
      title: 'Profit Margin Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '💰 Profit Margin Analysis', description: 'Analyze profitability at the item level. See which products generate the highest margins and which ones might need price adjustments.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Margin Table', description: 'Shows each item with its cost price, selling price, margin amount, and margin percentage. Sort by margin to find your most and least profitable items.', position: 'top' } });
        return s;
      }
    },
    '/reports/inventory-valuation/': {
      title: 'Inventory Valuation Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📊 Inventory Valuation', description: 'Calculate the total value of your current inventory based on cost price. This is the number that appears as "Inventory Value" on your dashboard.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Valuation Table', description: 'Shows each item with quantity on hand, cost per unit, and total value (qty × cost). The grand total at the bottom represents your total inventory investment.', position: 'top' } });
        return s;
      }
    },
    '/reports/': {
      title: 'Reports Hub Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📊 Reports Hub', description: 'Your central hub for all business reports. Choose from financial reports, inventory reports, and sales analytics to gain insights into your business performance.', position: 'center' } });
        return s;
      }
    },

    /* ── Reports: Sales ───────────────────────────────────────────────── */
    '/reports/sales/': {
      title: 'Sales Report Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📊 Sales Report', description: 'Analyze your sales performance by date, channel, and product. Filter by date range and channel, and group by daily or monthly periods.', position: 'center' } });
        if (exists('form')) s.push({ element: 'form', popover: { title: '🔍 Report Filters', description: 'Select a date range, sales channel, and grouping (Daily or Monthly) then click Apply to generate the report.', position: 'bottom' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Sales Data', description: 'Shows sales grouped by the selected period — including date, number of transactions, total revenue, cost, and profit for each period.', position: 'top' } });
        return s;
      }
    },

    /* ── Reports: Expenses ────────────────────────────────────────────── */
    '/reports/expenses/': {
      title: 'Expense Report Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📊 Expense Report', description: 'View expense trends over time and by category. The bar chart shows expense amounts by period, and the doughnut chart shows the category breakdown.', position: 'center' } });
        if (exists('form')) s.push({ element: 'form', popover: { title: '🔍 Report Filters', description: 'Filter expenses by date range and category. Choose daily or monthly grouping to see trends.', position: 'bottom' } });
        if (exists('canvas')) s.push({ element: 'canvas', popover: { title: '📈 Expense Charts', description: 'Visual breakdown of expenses by period (bar chart) and by category (doughnut chart).', position: 'top' } });
        return s;
      }
    },

    /* ── Reports: Financial Statement ─────────────────────────────────── */
    '/reports/financial-statement/': {
      title: 'Financial Statement Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📊 Profit & Loss Statement', description: 'Your comprehensive financial overview showing Revenue, Cost of Goods Sold (COGS), Gross Profit, Operating Expenses (OPEX), and Net Profit. All values in Philippine Peso (₱).', position: 'center' } });
        if (exists('.pnl-table')) s.push({ element: '.pnl-table', popover: { title: '📋 P&L Breakdown', description: '<strong>How it\'s calculated:</strong><br>1. Revenue = Total POS Sales<br>2. COGS = Inventory cost + COGS-category expenses<br>3. Gross Profit = Revenue - COGS<br>4. OPEX = Non-COGS category expenses<br>5. Net Profit = Gross Profit - OPEX', position: 'right' } });
        if (exists('#trendChart')) s.push({ element: '#trendChart', popover: { title: '📈 Monthly Trend', description: 'Stacked bar chart showing monthly revenue vs. expenses, with a profit line overlay. Use this to spot growth or declining trends.', position: 'top' } });
        return s;
      }
    },

    /* ── Core: Settings ───────────────────────────────────────────────── */
    '/core/settings/': {
      title: 'Settings Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '⚙️ Business Settings', description: 'This page lets you configure your business profile. All fields marked with * are required. Your business name and address appear on invoices and receipts.', position: 'center' } });
        if (exists('.card-primary')) s.push({ element: '.card-primary', popover: { title: '📝 Business Profile Form', description: 'Fill in your business name, address, phone, email, and TIN. You can also upload a logo that appears on invoices.', position: 'right' } });
        if (exists('.card-info')) s.push({ element: '.card-info', popover: { title: '✅ Setup Checklist', description: 'Quick links to configure essential items: Sales Channels, Expense Categories, Product Categories, Units, and Supply Categories.', position: 'left' } });
        return s;
      }
    },

    /* ── Core: Dictionary ──────────────────────────────────────────────── */
    '/core/dictionary/': {
      title: 'Dictionary Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📖 Business Terms Dictionary', description: '<p>Welcome to the <strong>Dictionary</strong> — your quick reference guide for all business terms used in WIS.</p><p>This page explains <strong>50+ terms</strong> across 12 modules with clear descriptions and practical examples.</p>', position: 'center' } });
        if (exists('#dictSearchBox')) s.push({ element: '#dictSearchBox', popover: { title: '🔍 Search Terms', description: 'Use the search bar to instantly filter terms by name, description, or example. Type keywords like "stock", "invoice", or "COGS" to find what you need.', position: 'bottom' } });
        if (exists('#dictTabs')) s.push({ element: '#dictTabs', popover: { title: '📑 Module Tabs', description: 'Terms are organized into <strong>12 modules</strong>: Catalog, Partners, Warehouses, Procurement, Sales, Inventory, POS, Pricing, Expenses, Supplies, QR Codes, Reports, and General. Click any tab to view terms for that module.', position: 'bottom' } });
        if (exists('#mod-catalog')) s.push({ element: '#mod-catalog', popover: { title: '📦 Term Details', description: 'Each term includes:<ul style="padding-left:1.2rem;margin-top:.5rem;"><li><strong>Name</strong> with an icon</li><li><strong>Description</strong> explaining what it means</li><li><strong>Example</strong> showing real-world usage</li></ul><p class="mb-0">Scroll through to learn about Items, Categories, SKUs, Reorder Points, and more!</p>', position: 'top' } });
        if (exists('#dictCount')) s.push({ element: '#dictCount', popover: { title: '📊 Term Counter', description: 'The counter shows how many terms are visible. When you search, it updates to show matching results vs total terms.', position: 'top' } });
        s.push({ popover: { title: '💡 Pro Tip', description: '<p><strong>Bookmark this page</strong> for quick reference when you encounter unfamiliar terms!</p><p>All terms are frontend-focused — no technical backend jargon, just business concepts you need to know.</p>', position: 'center' } });
        return s;
      }
    },

    /* ── Core: Channels ───────────────────────────────────────────────── */
    '/core/channels/new/': { title: 'New Channel Guide', steps: function () { return [{ popover: { title: '➕ New Sales Channel', description: 'Create a sales channel to track where your revenue comes from — e.g., Physical Store, Shopee, Lazada, Website. Channels appear in POS checkout and sales reports.', position: 'center' } }]; } },
    '/core/channels/': {
      title: 'Sales Channels Guide',
      steps: function () {
        return [
          { popover: { title: '📡 Sales Channels', description: 'Sales channels represent <strong>where your sales come from</strong> (e.g., Physical Store, Online Shop, Marketplace). They help you track revenue by source in reports.', position: 'center' } },
          { element: '.card', popover: { title: '📋 Channel List', description: 'Each channel has a <strong>code</strong> (short identifier) and <strong>name</strong>. Click Edit to modify or Trash to delete. Use "New Channel" to add more.', position: 'bottom' } },
        ];
      }
    },

    /* ── Core: Expense Categories ─────────────────────────────────────── */
    '/core/expense-categories/new/': { title: 'New Expense Category Guide', steps: function () { return [{ popover: { title: '➕ New Expense Category', description: 'Create a category for organizing expenses. <strong>Important:</strong> Check the "Is COGS" box if this category represents a Cost of Goods Sold (e.g., packaging, shipping). Otherwise, it is treated as an Operating Expense (OPEX).', position: 'center' } }]; } },
    '/core/expense-categories/': {
      title: 'Expense Categories Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📂 Expense Categories', description: 'Categories organize your expenses. The <strong>is_cogs</strong> flag is important: categories marked as COGS are included in Cost of Goods Sold on the financial statement, affecting your gross profit calculation.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Category List', description: 'Shows each category with its name and COGS flag. COGS categories affect your gross profit; OPEX categories are deducted after gross profit.', position: 'top' } });
        return s;
      }
    },

    /* ── Core: Expenses ───────────────────────────────────────────────── */
    '/core/expenses/new/': { title: 'New Expense Guide', steps: function () { return [{ popover: { title: '➕ Record Expense', description: 'Record a business expense. Select a category (COGS or OPEX), enter the amount, date, vendor, and optional reference number. This expense will appear in the Expense Report and Financial Statement.', position: 'center' } }]; } },
    '/core/expenses/': {
      title: 'Expenses Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🧾 Expense Tracking', description: 'Record all business expenses here. Each expense is linked to a category (COGS or OPEX) which determines how it appears in your financial statements.', position: 'center' } });
        if (exists('form')) s.push({ element: 'form', popover: { title: '🔍 Filters', description: 'Filter expenses by category or date range to find specific transactions quickly.', position: 'bottom' } });
        if (exists('.alert-info')) s.push({ element: '.alert-info', popover: { title: '💰 Total', description: 'Shows the total amount for the current filter selection.', position: 'bottom' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Expense Table', description: 'Each row shows the date, category (with COGS/OPEX badge), amount, vendor, reference number, and who recorded it. Use the edit/delete buttons on the right.', position: 'top' } });
        return s;
      }
    },

    /* ── Core: Supply Categories ──────────────────────────────────────── */
    '/core/supply-categories/new/': { title: 'New Supply Category Guide', steps: function () { return [{ popover: { title: '➕ New Supply Category', description: 'Create a category to group your supply items — e.g., Office Supplies, Cleaning Materials, Packaging. This helps organize and filter your supplies inventory.', position: 'center' } }]; } },
    '/core/supply-categories/': {
      title: 'Supply Categories Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📂 Supply Categories', description: 'Categories for organizing your consumable supplies. Examples: Office Supplies, Cleaning, Packaging, Safety Equipment.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Category List', description: 'Shows each supply category name. Use the action buttons to edit or delete.', position: 'top' } });
        return s;
      }
    },

    /* ── Core: Supplies ───────────────────────────────────────────────── */
    '/core/supplies/new/': { title: 'New Supply Item Guide', steps: function () { return [{ popover: { title: '➕ Add Supply Item', description: 'Add a new consumable supply to track. Set the name, category, minimum stock level (triggers alerts), and cost per unit.', position: 'center' } }]; } },
    '/core/supplies/': {
      title: 'Supplies Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '📋 Supplies Inventory', description: 'Track consumable supplies separately from your main product inventory. Supplies include office supplies, cleaning materials, packaging, etc.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📊 Supply Items Table', description: 'Shows each supply item with current stock, minimum stock level, and cost per unit. Items highlighted in <strong class="text-danger">red</strong> are below minimum stock level.', position: 'top' } });
        return s;
      }
    },

    /* ── Core: Supply Movements ───────────────────────────────────────── */
    '/core/supply-movements/new/': { title: 'New Movement Guide', steps: function () { return [{ popover: { title: '➕ Record Supply Movement', description: 'Record a stock-in (purchase/received) or stock-out (used/consumed) for a supply item. This updates the current stock level automatically.', position: 'center' } }]; } },
    '/core/supply-movements/': {
      title: 'Supply Movements Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🔄 Supply Movements', description: 'Track all stock-in and stock-out movements for your supply items. Each movement automatically updates the current stock balance for the supply.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Movement History', description: 'Shows each movement with the supply item, type (IN/OUT), quantity, date, and notes. Use this to audit supply usage over time.', position: 'top' } });
        return s;
      }
    },

    /* /core/invoices/ (list + detail) — see Detail & Sub-page section below */

    /* ── Core: Goals ──────────────────────────────────────────────────── */
    '/core/goals/new/': { title: 'New Goal Guide', steps: function () { return [{ popover: { title: '➕ Create Target Goal', description: 'Set a measurable business target. Define the goal type (Revenue, Sales Count, Custom), target value, due date, priority, and optionally assign it to a team member.', position: 'center' } }]; } },

    /* ── Detail & Sub-page Guides (matched via prefix) ───────────────── */

    /* Item Detail (/catalog/items/<id>/) — matched via prefix from /catalog/items/ */
    /* PO Detail */
    '/procurement/purchase-orders/': {
      title: 'Purchase Orders Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        // Detail page: /procurement/purchase-orders/<id>/
        if (path.match(/\/procurement\/purchase-orders\/\d+\//)) {
          s.push({ popover: { title: '📋 Purchase Order Details', description: 'This page shows the full details of a Purchase Order including supplier info, dates, status, and all ordered line items with quantities and prices.', position: 'center' } });
          if (exists('.btn-warning')) s.push({ element: '.btn-warning', popover: { title: '✏️ Edit (Draft Only)', description: 'You can only edit a PO while it is in <strong>DRAFT</strong> status. Once posted, it becomes read-only.', position: 'bottom' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📄 Order Info', description: 'Shows PO number, status, supplier, warehouse, dates, and notes. The status badge indicates the current workflow stage.', position: 'right' } });
          if (exists('.table-hover')) s.push({ element: '.table-hover', popover: { title: '📦 Order Lines', description: 'Each line shows the item, qty ordered, qty received (from GRNs), remaining qty, unit price, and line total.', position: 'top' } });
          return s;
        }
        // Edit page
        if (path.match(/\/edit\//)) {
          s.push({ popover: { title: '✏️ Edit Purchase Order', description: 'Modify this draft PO. You can change the supplier, dates, notes, and update line items with quantities and prices.', position: 'center' } });
          return s;
        }
        // Create page
        if (path.indexOf('/create/') !== -1) {
          s.push({ popover: { title: '➕ New Purchase Order', description: 'Create a PO to order goods from a supplier. Select the supplier, add line items with quantities and prices, then save as DRAFT. Post it when you\'re ready to commit.', position: 'center' } });
          if (exists('[name="supplier"]')) s.push({ element: '[name="supplier"]', popover: { title: '🤝 Select Supplier', description: 'Choose the supplier (vendor) you are ordering from. The supplier must be created in the Partners module first.', position: 'right' } });
          return s;
        }
        // List page
        s.push({ popover: { title: '📋 Purchase Orders', description: 'Purchase Orders (POs) are formal requests to buy goods from suppliers. <strong>Workflow:</strong> Create PO → Post PO → Create Goods Receipt to receive the items into your warehouse.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 PO List', description: 'Shows PO number, supplier, date, status (DRAFT/POSTED/CANCELLED), and total amount. Click the PO number for details. Only DRAFT POs can be edited.', position: 'top' } });
        return s;
      }
    },

    /* GRN Detail */
    '/procurement/goods-receipts/': {
      title: 'Goods Receipts Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        if (path.match(/\/procurement\/goods-receipts\/\d+\//)) {
          s.push({ popover: { title: '📦 Goods Receipt Details', description: 'Full details of this GRN — linked PO, supplier, receiving warehouse, receipt date, and all line items with received quantities.', position: 'center' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📄 GRN Info', description: 'Shows GRN number, status, linked PO, supplier, warehouse, dates, and who posted it. <strong>POSTED</strong> GRNs have already increased your stock.', position: 'right' } });
          if (exists('.table-hover')) s.push({ element: '.table-hover', popover: { title: '📦 Receipt Lines', description: 'Each line shows the item, receiving location, quantity, unit, batch/serial numbers, and notes.', position: 'top' } });
          return s;
        }
        if (path.indexOf('/create/') !== -1) {
          s.push({ popover: { title: '➕ New Goods Receipt (GRN)', description: 'Record incoming goods from a supplier. Link it to a Purchase Order, specify the receiving warehouse and location, then add the items with received quantities.', position: 'center' } });
          return s;
        }
        s.push({ popover: { title: '📦 Goods Receipts (GRN)', description: 'Goods Receipts record when physical items arrive at your warehouse. <strong>Posting a GRN increases stock balance</strong> at the target location.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 GRN List', description: 'Shows GRN number, related PO, warehouse, status, and date. POSTED GRNs have updated your stock.', position: 'top' } });
        return s;
      }
    },

    /* SO Detail */
    '/sales/orders/': {
      title: 'Sales Orders Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        if (path.match(/\/sales\/orders\/\d+\//)) {
          s.push({ popover: { title: '🛒 Sales Order Details', description: 'Full details of this SO — customer info, dates, status, shipping address, and all ordered line items with quantities, prices, and delivery status.', position: 'center' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📄 Order Info', description: 'Shows SO number, status, customer, warehouse, dates, shipping address, and notes.', position: 'right' } });
          if (exists('.table-hover')) s.push({ element: '.table-hover', popover: { title: '📦 Order Lines', description: 'Each line shows the item, qty ordered, qty delivered, qty reserved, remaining, unit price, and line total.', position: 'top' } });
          return s;
        }
        if (path.indexOf('/create/') !== -1) {
          s.push({ popover: { title: '➕ New Sales Order', description: 'Create a sales order for a customer. Select the customer, add products with quantities and prices, then save as DRAFT.', position: 'center' } });
          return s;
        }
        s.push({ popover: { title: '🛒 Sales Orders', description: 'Sales Orders (SOs) are formal orders from your customers. <strong>Workflow:</strong> Create SO → Post SO → Create Delivery Note → Generate Invoice.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 SO List', description: 'Shows SO number, customer, date, status (DRAFT/POSTED/CANCELLED), and total.', position: 'top' } });
        return s;
      }
    },

    /* Delivery Detail */
    '/sales/deliveries/': {
      title: 'Deliveries Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        if (path.match(/\/sales\/deliveries\/\d+\//)) {
          s.push({ popover: { title: '🚚 Delivery Note Details', description: 'Full details of this delivery — linked SO, customer, warehouse, driver/vehicle info, and all delivered line items.', position: 'center' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📄 Delivery Info', description: 'Shows DN number, status, linked SO, customer, warehouse, delivery date, driver, vehicle, and shipping address.', position: 'right' } });
          if (exists('.table-hover')) s.push({ element: '.table-hover', popover: { title: '📦 Delivery Lines', description: 'Each line shows the item, source location, delivered quantity, unit, and notes.', position: 'top' } });
          return s;
        }
        if (path.indexOf('/create/') !== -1) {
          s.push({ popover: { title: '➕ New Delivery Note', description: 'Record outgoing shipments to customers. Link to a Sales Order, select the source warehouse and location, then add items with delivered quantities.', position: 'center' } });
          return s;
        }
        s.push({ popover: { title: '🚚 Delivery Notes', description: 'Delivery Notes record when goods leave your warehouse to reach customers. <strong>Posting a delivery decreases stock balance</strong>.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Delivery List', description: 'Shows delivery number, related SO, customer, warehouse, status, and date.', position: 'top' } });
        return s;
      }
    },

    /* Warehouse Detail */
    '/warehouses/': {
      title: 'Warehouses Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        // Skip locations path — handled by its own entry
        if (path.indexOf('/locations/') !== -1) return s;
        if (path.match(/\/warehouses\/\d+\//)) {
          s.push({ popover: { title: '🏭 Warehouse Details', description: 'View this warehouse\'s information, its locations (bins/shelves), and current stock levels across all locations.', position: 'center' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📄 Warehouse Info', description: 'Shows warehouse code, name, city, address, phone, manager, and whether negative stock is allowed.', position: 'right' } });
          var locTable = document.querySelectorAll('.table-hover');
          if (locTable.length > 0) s.push({ element: locTable[0], popover: { title: '📍 Locations', description: 'All storage locations within this warehouse. Click "Add Location" to create bins, shelves, or zones.', position: 'top' } });
          if (locTable.length > 1) s.push({ element: locTable[1], popover: { title: '📦 Stock Balances', description: 'Current inventory levels by item and location within this warehouse.', position: 'top' } });
          return s;
        }
        if (path.indexOf('/create/') !== -1) {
          s.push({ popover: { title: '➕ Add Warehouse', description: 'Create a new warehouse or storage facility. After creating it, add locations (bins/shelves) to start tracking inventory.', position: 'center' } });
          return s;
        }
        s.push({ popover: { title: '🏭 Warehouse Management', description: 'Warehouses are your physical storage facilities. Each contains locations where items are stored.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Warehouse List', description: 'Shows all warehouses with their code, name, and address. Click to see details and locations.', position: 'top' } });
        return s;
      }
    },

    /* Invoice Detail (/core/invoices/<id>/) */
    '/core/invoices/': {
      title: 'Invoices Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        if (path.match(/\/core\/invoices\/\d+\//)) {
          // Check if it's print page
          if (path.indexOf('/print/') !== -1) {
            s.push({ popover: { title: '🖨️ Print Invoice', description: 'This is the printable version of the invoice. Use your browser\'s print function (Ctrl+P) to print or save as PDF.', position: 'center' } });
            return s;
          }
          s.push({ popover: { title: '🧾 Invoice Details', description: 'Full invoice view with business header, customer billing info, line items, subtotal, discounts, tax, and grand total.', position: 'center' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📋 Line Items & Totals', description: 'Shows each item with code, description, qty, unit price, discount, and line total. The footer shows subtotal, discount, tax, and grand total.', position: 'top' } });
          return s;
        }
        s.push({ popover: { title: '🧾 Invoice Management', description: 'Invoices are generated from POS sales or Sales Orders. Each includes line items, subtotal, discounts, tax, and grand total.', position: 'center' } });
        if (exists('.small-box')) s.push({ element: '.small-box', popover: { title: '📊 Invoice Summary', description: 'Quick stats showing total invoices and total billed amount.', position: 'bottom' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Invoice List', description: 'Click any invoice to view details. Use eye icon to view or printer icon to print.', position: 'top' } });
        return s;
      }
    },

    /* POS Receipt Detail (/pos/receipts/<id>/) */
    '/pos/receipts/': {
      title: 'Receipts Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        if (path.match(/\/pos\/receipts\/\d+\//)) {
          s.push({ popover: { title: '🧾 Receipt Details', description: 'Full POS receipt showing sale details, totals, payment methods, and all line items sold.', position: 'center' } });
          if (exists('.table-bordered')) {
            var tables = document.querySelectorAll('.table-bordered');
            if (tables.length > 0) s.push({ element: tables[0], popover: { title: '📄 Sale Info', description: 'Shows sale number, status, register, customer, warehouse, date, and posting time.', position: 'right' } });
            if (tables.length > 1) s.push({ element: tables[1], popover: { title: '💰 Totals & Payments', description: 'Subtotal, discount, tax, grand total, and payment breakdown by method (Cash, Card, etc.).', position: 'left' } });
          }
          return s;
        }
        s.push({ popover: { title: '🧾 POS Receipts', description: 'Browse all completed POS sales. Each receipt shows items sold, payment method, and can be reprinted or used to generate an invoice.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Receipt List', description: 'Shows receipt number, date, total, status, and shift. Click for full details.', position: 'top' } });
        return s;
      }
    },

    /* POS Shift Summary (/pos/shifts/<id>/summary/) */
    '/pos/shifts/': {
      title: 'POS Shifts Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        if (path.match(/\/pos\/shifts\/\d+/)) {
          s.push({ popover: { title: '📊 Shift Summary', description: 'Detailed breakdown of this POS shift — opening/closing cash, total sales, transaction count, and cash variance.', position: 'center' } });
          return s;
        }
        if (path.indexOf('/open/') !== -1) {
          s.push({ popover: { title: '🔓 Open a POS Shift', description: 'Select a register, enter opening cash, and start the shift. You must have an open shift to make POS sales.', position: 'center' } });
          return s;
        }
        s.push({ popover: { title: '🕐 Shift History', description: 'View all POS shifts — open and closed. Each tracks the cashier, register, times, cash totals, and sales.', position: 'center' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Shift List', description: 'Shows shift ID, register, cashier, status, opening time, and total sales.', position: 'top' } });
        return s;
      }
    },

    /* Catalog Item — handles list, detail, create, edit via path detection */
    '/catalog/items/': {
      title: 'Items Guide',
      steps: function () {
        var s = [];
        var path = window.location.pathname;
        // Detail page: /catalog/items/<id>/
        if (path.match(/\/catalog\/items\/\d+\/$/)) {
          s.push({ popover: { title: '📦 Item Details', description: 'Complete item profile showing code, name, type, category, pricing, stock levels, current stock by location, and recent stock movements.', position: 'center' } });
          if (exists('.table-bordered')) s.push({ element: '.table-bordered', popover: { title: '📄 Item Info', description: 'All item attributes: code, name, type, category, unit, barcode, cost/selling price, margin, and stock thresholds.', position: 'right' } });
          var tables = document.querySelectorAll('.table-hover');
          if (tables.length > 0) s.push({ element: tables[0], popover: { title: '📍 Stock by Location', description: 'Current stock levels at each warehouse location — on hand, reserved, and available quantities.', position: 'top' } });
          if (tables.length > 1) s.push({ element: tables[1], popover: { title: '🔄 Recent Movements', description: 'Latest stock movements for this item — receipts, deliveries, transfers, adjustments, and POS sales.', position: 'top' } });
          return s;
        }
        // Edit page
        if (path.match(/\/catalog\/items\/\d+\/edit\//)) {
          s.push({ popover: { title: '✏️ Edit Item', description: 'Update this item\'s details. Fields are grouped into Identity, Pricing, Stock Levels, and Additional Info for easier editing.', position: 'center' } });
          return s;
        }
        // Create page
        if (path.indexOf('/create/') !== -1) {
          s.push({ popover: { title: '➕ Create New Item', description: 'Fill in the form to add a new product or service. Fields are grouped: Identity (code, name, type), Pricing (cost, selling), Stock Levels (min, max, reorder), and Additional Info.', position: 'center' } });
          return s;
        }
        // List page
        s.push({ popover: { title: '📦 Item Master List', description: 'Your product catalog — all items, raw materials, and services. Use the search and sort to find items quickly.', position: 'center' } });
        if (exists('.btn-primary')) s.push({ element: '.btn-primary', popover: { title: '➕ New Item', description: 'Click to add a new product, raw material, or service.', position: 'left' } });
        if (exists('table')) s.push({ element: 'table', popover: { title: '📋 Item Table', description: 'Shows Code, Name, Type, Category, Unit, and Status. Use DataTables search and pagination to navigate. Click any code to view details.', position: 'top' } });
        return s;
      }
    },

    '/core/goals/': {
      title: 'Target Goals Guide',
      steps: function () {
        var s = [];
        s.push({ popover: { title: '🎯 Target Goals', description: 'Set measurable business goals to keep your team focused. Goals can be revenue targets, sales targets, or any custom metric. Track progress visually with progress bars.', position: 'center' } });
        if (exists('select[name="status"]')) s.push({ element: 'select[name="status"]', popover: { title: '🔍 Status Filter', description: 'Filter goals by status: Pending, In Progress, Completed, or Cancelled.', position: 'bottom' } });
        if (exists('.goal-card')) s.push({ element: '.goal-card', popover: { title: '📋 Goal Card', description: 'Each card shows the goal title, priority badge, status, progress bar, and due date. <strong class="text-danger">Red dates</strong> mean overdue. <strong class="text-warning">Yellow dates</strong> mean due within 7 days.', position: 'bottom' } });
        return s;
      }
    },
  };

  /* ═══════════════════════════════════════════════════════════════════════
   * DRIVER.JS INTEGRATION
   * ═══════════════════════════════════════════════════════════════════════ */

  function startFullTour() {
    // Ensure sidebar is open for the tour
    var body = document.body;
    if (body.classList.contains('sidebar-collapse')) {
      body.classList.remove('sidebar-collapse');
    }
    // Ensure all nav-treeview items are visible for sidebar steps
    elAll('.nav-sidebar .nav-item').forEach(function (li) {
      if (!li.classList.contains('menu-open') && li.querySelector('.nav-treeview')) {
        li.classList.add('menu-open');
      }
    });

    var steps = buildFullTourSteps();
    if (steps.length === 0) return;

    var driver = new window.driver.js.driver({
      showProgress: true,
      animate: true,
      allowClose: true,
      overlayColor: 'rgba(0,0,0,0.6)',
      stagePadding: 8,
      stageRadius: 8,
      popoverClass: 'wis-tour-popover',
      nextBtnText: 'Next →',
      prevBtnText: '← Back',
      doneBtnText: 'Finish ✓',
      progressText: 'Step {{current}} of {{total}}',
      onDestroyStarted: function () {
        markFullTourDone();
        if (driver.hasNextStep()) {
          // User clicked X or overlay — confirm skip
          if (confirm('Skip the rest of the tour? You can replay it anytime from the Help button.')) {
            driver.destroy();
          }
          return;
        }
        driver.destroy();
      },
      steps: steps,
    });

    driver.drive();
  }

  function startSectionTour(pathKey) {
    var tourDef = null;

    // Try exact match first, then longest prefix match
    if (pageTours[pathKey]) {
      tourDef = pageTours[pathKey];
    } else {
      // Find longest matching prefix (avoids /warehouses/ matching before /warehouses/locations/)
      var bestKey = '';
      for (var key in pageTours) {
        if (pathKey.indexOf(key) === 0 && key.length > bestKey.length) {
          bestKey = key;
        }
      }
      if (bestKey) tourDef = pageTours[bestKey];
    }

    if (!tourDef) {
      // Generic fallback
      var driver = new window.driver.js.driver({
        showProgress: false,
        steps: [{
          popover: {
            title: 'ℹ️ Page Guide',
            description: 'No specific guide is available for this page yet. Use the <strong>Help</strong> button in the top bar to take the full system tour.',
            position: 'center',
          }
        }],
      });
      driver.drive();
      return;
    }

    var steps = tourDef.steps();
    if (steps.length === 0) return;

    var driver = new window.driver.js.driver({
      showProgress: steps.length > 1,
      animate: true,
      allowClose: true,
      overlayColor: 'rgba(0,0,0,0.55)',
      stagePadding: 8,
      stageRadius: 8,
      popoverClass: 'wis-tour-popover',
      nextBtnText: 'Next →',
      prevBtnText: '← Back',
      doneBtnText: 'Got it ✓',
      progressText: '{{current}} / {{total}}',
      steps: steps,
    });
    driver.drive();
  }

  /* ═══════════════════════════════════════════════════════════════════════
   * INITIALIZATION
   * ═══════════════════════════════════════════════════════════════════════ */
  function init() {
    // Bind replay button
    var replayBtn = el('#wis-tour-replay');
    if (replayBtn) {
      replayBtn.addEventListener('click', function (e) {
        e.preventDefault();
        // Navigate to dashboard if not already there
        if (window.location.pathname !== '/dashboard/') {
          window.location.href = '/dashboard/?tour=replay';
          return;
        }
        startFullTour();
      });
    }

    // Bind page-specific guide button
    var pageGuideBtn = el('#wis-page-guide');
    if (pageGuideBtn) {
      pageGuideBtn.addEventListener('click', function (e) {
        e.preventDefault();
        startSectionTour(window.location.pathname);
      });
    }

    // Auto-start full tour for new users on dashboard
    var isDashboard = window.location.pathname === '/dashboard/';
    var isReplay = window.location.search.indexOf('tour=replay') !== -1;

    if (isDashboard && (isReplay || !isFullTourDone())) {
      // Small delay to let the page render fully
      setTimeout(function () {
        startFullTour();
      }, 600);
    }
  }

  // Expose for external use
  window.WISTour = {
    startFullTour: startFullTour,
    startSectionTour: startSectionTour,
    resetTour: resetFullTour,
    isCompleted: isFullTourDone,
  };

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
