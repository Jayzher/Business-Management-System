/**
 * ws-sync.js — WebSocket real-time sync client for the web dashboard.
 *
 * Connects to ws(s)://<host>/ws/sync/ using the Django session cookie.
 * When the server broadcasts a table_changed event, the page content is
 * refreshed automatically via WIS.refreshContent() (already defined in
 * base.html).
 *
 * Features:
 *   - Auto-reconnect with exponential backoff (1s → 30s max)
 *   - Visual connection indicator in the navbar
 *   - Toast notifications on data changes
 *   - Debounced refresh to batch rapid-fire events
 *   - Subscribe to specific tables per page (optional)
 *
 * Usage:
 *   The script auto-initializes on DOMContentLoaded.
 *   Pages can customize behavior via data attributes on <body>:
 *     data-ws-tables="catalog_item,inventory_stockbalance"  — subscribe to specific tables
 *     data-ws-no-refresh="true"                             — disable auto-refresh
 */

(function () {
  'use strict';

  // ── Configuration ─────────────────────────────────────────────────
  var RECONNECT_BASE = 1000;       // Initial reconnect delay (ms)
  var RECONNECT_MAX  = 30000;      // Max reconnect delay (ms)
  var REFRESH_DEBOUNCE = 800;      // Debounce rapid table_changed events (ms)
  var PING_INTERVAL  = 25000;      // Keepalive ping every 25s

  // ── State ─────────────────────────────────────────────────────────
  var ws = null;
  var reconnectDelay = RECONNECT_BASE;
  var reconnectTimer = null;
  var pingTimer = null;
  var refreshTimer = null;
  var pendingTables = [];
  var isConnected = false;

  // ── Helpers ───────────────────────────────────────────────────────
  function getWsUrl() {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return protocol + '//' + window.location.host + '/ws/sync/';
  }

  function log(msg) {
    if (window.console && console.debug) console.debug('[WS-Sync]', msg);
  }

  // ── Connection indicator ──────────────────────────────────────────
  function updateIndicator(connected) {
    isConnected = connected;
    var el = document.getElementById('ws-status-indicator');
    if (!el) return;
    if (connected) {
      el.className = 'fas fa-circle text-success';
      el.title = 'Real-time: connected';
    } else {
      el.className = 'fas fa-circle text-danger';
      el.title = 'Real-time: disconnected';
    }
  }

  // ── Debounced page refresh ────────────────────────────────────────
  function scheduleRefresh(tables) {
    // Accumulate tables
    for (var i = 0; i < tables.length; i++) {
      if (pendingTables.indexOf(tables[i]) === -1) {
        pendingTables.push(tables[i]);
      }
    }
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      var changed = pendingTables.slice();
      pendingTables = [];

      // Check if page opts out of auto-refresh
      var body = document.body;
      if (body && body.dataset && body.dataset.wsNoRefresh === 'true') {
        log('Auto-refresh disabled for this page');
        return;
      }

      // Fire custom event so individual pages can react
      var evt = new CustomEvent('ws:table-changed', { detail: { tables: changed } });
      document.dispatchEvent(evt);

      // Default: refresh the page content area
      if (typeof WIS !== 'undefined' && typeof WIS.refreshContent === 'function') {
        log('Refreshing content for: ' + changed.join(', '));
        WIS.refreshContent();
      }

      // Show a subtle toast
      if (typeof WIS !== 'undefined' && typeof WIS.toast === 'function') {
        WIS.toast('Data updated', 'info');
      }
    }, REFRESH_DEBOUNCE);
  }

  // ── WebSocket lifecycle ───────────────────────────────────────────
  function connect() {
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
      return;
    }

    var url = getWsUrl();
    log('Connecting to ' + url);
    ws = new WebSocket(url);

    ws.onopen = function () {
      log('Connected');
      reconnectDelay = RECONNECT_BASE;
      updateIndicator(true);

      // Subscribe to page-specific tables if configured
      var body = document.body;
      if (body && body.dataset && body.dataset.wsTables) {
        var tables = body.dataset.wsTables.split(',').map(function (t) { return t.trim(); });
        ws.send(JSON.stringify({ action: 'subscribe', tables: tables }));
        log('Subscribed to: ' + tables.join(', '));
      }

      // Start keepalive pings
      clearInterval(pingTimer);
      pingTimer = setInterval(function () {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'ping' }));
        }
      }, PING_INTERVAL);
    };

    ws.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        log('Received: ' + JSON.stringify(data));

        if (data.type === 'table_changed' && Array.isArray(data.tables)) {
          scheduleRefresh(data.tables);
        }
        // 'connected', 'subscribed', 'pong' are informational — no action needed
      } catch (e) {
        log('Parse error: ' + e);
      }
    };

    ws.onclose = function (event) {
      log('Disconnected (code=' + event.code + ')');
      updateIndicator(false);
      clearInterval(pingTimer);

      // Don't reconnect if server explicitly rejected auth
      if (event.code === 4001) {
        log('Auth rejected — not reconnecting');
        return;
      }

      // Exponential backoff reconnect
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(function () {
        reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX);
        connect();
      }, reconnectDelay);
      log('Reconnecting in ' + reconnectDelay + 'ms');
    };

    ws.onerror = function () {
      log('WebSocket error');
      // onclose will fire after this and handle reconnection
    };
  }

  // ── Public API ────────────────────────────────────────────────────
  window.WIS = window.WIS || {};

  /**
   * WIS.wsSubscribe(tables) — change the table subscription at runtime.
   * @param {string[]} tables — array of db_table names, or ['*'] for all.
   */
  WIS.wsSubscribe = function (tables) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: 'subscribe', tables: tables }));
    }
  };

  /**
   * WIS.wsConnected — check if the WebSocket is currently connected.
   */
  Object.defineProperty(WIS, 'wsConnected', {
    get: function () { return isConnected; },
  });

  // ── Initialize on DOM ready ───────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
})();
