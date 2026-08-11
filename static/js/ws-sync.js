/**
 * ws-sync.js — WebSocket real-time sync client for the web dashboard.
 *
 * Connects to ws(s)://<host>/ws/sync/ using the Django session cookie.
 * When the server broadcasts a table_changed or data_changed event,
 * the page content is refreshed automatically.
 *
 * Features:
 *   - Auto-reconnect with exponential backoff (1s → 30s max)
 *   - Auto catch-up on reconnect: fetches missed changes from server
 *   - Visual connection indicator in the navbar
 *   - Toast notifications on data changes
 *   - Debounced refresh to batch rapid-fire events
 *   - Subscribe to specific tables per page (optional)
 *   - Tracks last-seen timestamp in sessionStorage for gap detection
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
  var REFRESH_DEBOUNCE = 800;      // Debounce rapid events (ms)
  var REFRESH_MAX_WAIT = 4000;     // Upper bound on how long a sustained event
                                    // flood (e.g. a bulk sync trickling through
                                    // the background worker) can keep postponing
                                    // a refresh — without this, continuous events
                                    // spaced under REFRESH_DEBOUNCE apart reset
                                    // the debounce forever and the page never
                                    // settles enough to scroll.
  var PING_INTERVAL  = 25000;      // Keepalive ping every 25s
  var CATCHUP_URL    = '/api/sync/catchup/';
  var STORAGE_KEY    = 'ws_sync_last_event_ms';
  var CLIENT_ID_KEY  = 'ws_sync_client_id';

  // ── State ─────────────────────────────────────────────────────────
  var ws = null;
  var reconnectDelay = RECONNECT_BASE;
  var reconnectTimer = null;
  var pingTimer = null;
  var refreshTimer = null;
  var refreshMaxWaitTimer = null;
  var pendingTables = [];
  var isConnected = false;
  var wasConnectedBefore = false;  // True after first successful connect
  var catchupInProgress = false;

  // ── Helpers ───────────────────────────────────────────────────────

  // A per-tab id (sessionStorage, not shared with other tabs even in the
  // same browser/session) sent to the server on every write this tab makes
  // — as a WS query param, a fetch() header, and a hidden form field — so
  // the server can tag the resulting broadcast with "this tab already
  // knows" and this same connection can skip re-refreshing itself over its
  // own change. See sync/middleware.py WsClientIdMiddleware and
  // sync/consumers.py SyncConsumer.data_changed for the server side.
  function getClientId() {
    try {
      var id = sessionStorage.getItem(CLIENT_ID_KEY);
      if (!id) {
        id = (window.crypto && window.crypto.randomUUID)
          ? window.crypto.randomUUID()
          : 'tab-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
        sessionStorage.setItem(CLIENT_ID_KEY, id);
      }
      return id;
    } catch (e) {
      return null; // sessionStorage unavailable — self-echo suppression just won't apply
    }
  }

  function getWsUrl() {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var clientId = getClientId();
    var qs = clientId ? ('?client_id=' + encodeURIComponent(clientId)) : '';
    return protocol + '//' + window.location.host + '/ws/sync/' + qs;
  }

  function log(msg) {
    if (window.console && console.debug) console.debug('[WS-Sync]', msg);
  }

  function getLastEventTime() {
    try {
      var val = sessionStorage.getItem(STORAGE_KEY);
      return val ? parseInt(val, 10) : null;
    } catch (e) { return null; }
  }

  function setLastEventTime(ms) {
    try {
      sessionStorage.setItem(STORAGE_KEY, String(ms));
    } catch (e) { /* ignore */ }
  }

  function getCsrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  // ── Attach the client id to every write this tab makes ─────────────
  // Two delivery paths, covering both ways this app submits data:
  //   1. fetch()-based AJAX (the modal/toolbar form-submit helpers in
  //      base.html) — add a request header.
  //   2. Plain <form> submissions that navigate the browser normally (no
  //      JS interception) — a header can't be attached to those, so inject
  //      a hidden input instead, before the browser sends the request.
  // Same-origin only, so this never leaks the id to third-party requests.

  function isSameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  (function patchFetchWithClientId() {
    if (!window.fetch || window.fetch.__wsClientIdPatched) return;
    var originalFetch = window.fetch;
    var patched = function (input, init) {
      try {
        var url = (typeof input === 'string') ? input : (input && input.url);
        var clientId = getClientId();
        if (clientId && url && isSameOrigin(url)) {
          init = init || {};
          var headers = new Headers(init.headers || (typeof input !== 'string' && input.headers) || {});
          headers.set('X-Ws-Client-Id', clientId);
          init = Object.assign({}, init, { headers: headers });
        }
      } catch (e) { /* fall through to unmodified call */ }
      return originalFetch.call(window, input, init);
    };
    patched.__wsClientIdPatched = true;
    window.fetch = patched;
  })();

  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || form.tagName !== 'FORM') return;
    var clientId = getClientId();
    if (!clientId) return;
    var input = form.querySelector('input[name="_ws_client_id"]');
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = '_ws_client_id';
      form.appendChild(input);
    }
    input.value = clientId;
  }, true /* capture phase — run before any bubble-phase submit handler
             (e.g. wisHandleFormSubmit) reads the form's field values */);

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
  function doRefresh() {
    clearTimeout(refreshTimer);
    clearTimeout(refreshMaxWaitTimer);
    refreshTimer = null;
    refreshMaxWaitTimer = null;

    var changed = pendingTables.slice();
    pendingTables = [];

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
  }

  function scheduleRefresh(tables) {
    for (var i = 0; i < tables.length; i++) {
      if (pendingTables.indexOf(tables[i]) === -1) {
        pendingTables.push(tables[i]);
      }
    }
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(doRefresh, REFRESH_DEBOUNCE);

    // A sustained flood of events (e.g. a bulk sync trickling through the
    // background worker, one broadcast per row/batch) keeps resetting the
    // debounce above before it ever fires, which would otherwise starve
    // the page of a refresh indefinitely — or, worse, let it fire back-to
    // -back the instant the flood pauses for a beat, reloading the content
    // area every second or so. This timer guarantees a refresh happens at
    // least once every REFRESH_MAX_WAIT ms regardless of how continuous
    // the event stream is, started on the first event of a burst.
    if (!refreshMaxWaitTimer) {
      refreshMaxWaitTimer = setTimeout(doRefresh, REFRESH_MAX_WAIT);
    }
  }

  // ── Catch-up: fetch missed changes after reconnect ────────────────
  function catchUp() {
    if (catchupInProgress) return;

    var lastMs = getLastEventTime();
    if (!lastMs && !wasConnectedBefore) {
      // First ever connection — no gap to fill, just record the time
      setLastEventTime(Date.now());
      return;
    }

    // If we have no timestamp but were connected before, force a refresh
    var url = CATCHUP_URL;
    if (lastMs) {
      url += '?since_ms=' + lastMs;
    }

    catchupInProgress = true;
    log('Catching up since ' + (lastMs ? new Date(lastMs).toISOString() : 'unknown'));

    fetch(url, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
    .then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function (data) {
      catchupInProgress = false;

      if (data.has_changes && data.changed_tables && data.changed_tables.length > 0) {
        log('Catch-up: ' + data.changed_tables.length + ' table(s) changed while offline');

        // Update the last-seen timestamp
        if (data.server_time_ms) {
          setLastEventTime(data.server_time_ms);
        }

        // Trigger a refresh for the changed tables
        if (data.changed_tables.indexOf('*') !== -1) {
          // Wildcard: refresh everything
          scheduleRefresh(['*']);
        } else {
          scheduleRefresh(data.changed_tables);
        }

        // Show a toast indicating catch-up happened
        if (typeof WIS !== 'undefined' && typeof WIS.toast === 'function') {
          WIS.toast('Synced ' + data.changed_tables.length + ' update(s) from server', 'success');
        }
      } else {
        log('Catch-up: no changes missed');
        if (data.server_time_ms) {
          setLastEventTime(data.server_time_ms);
        }
      }

      // Show outbox warning if there are pending entries
      if (data.outbox_pending > 0 && typeof WIS !== 'undefined' && typeof WIS.toast === 'function') {
        WIS.toast(data.outbox_pending + ' offline write(s) pending sync', 'warning');
      }
    })
    .catch(function (err) {
      catchupInProgress = false;
      log('Catch-up failed: ' + err);
      // On failure, just refresh the page to be safe
      scheduleRefresh(['*']);
    });
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

      // ── Auto catch-up on reconnect ──────────────────────────────
      // If we were connected before (i.e. this is a REconnect, not first
      // connect), fetch any changes we missed while disconnected.
      if (wasConnectedBefore) {
        catchUp();
      } else {
        // First connection — just record the server time
        wasConnectedBefore = true;
        setLastEventTime(Date.now());
      }
    };

    ws.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        log('Received: ' + JSON.stringify(data));

        if (data.type === 'table_changed' && Array.isArray(data.tables)) {
          setLastEventTime(Date.now());
          scheduleRefresh(data.tables);
        } else if (data.type === 'data_changed' && typeof data.table === 'string') {
          // Rich event with actual row data
          var detail = {
            table: data.table,
            action: data.action || 'upsert',
            rows: Array.isArray(data.rows) ? data.rows : [],
            timestamp: data.timestamp || '',
          };
          document.dispatchEvent(new CustomEvent('ws:data-changed', { detail: detail }));

          // Update last-seen time from the event timestamp
          if (data.timestamp) {
            var eventMs = new Date(data.timestamp).getTime();
            if (!isNaN(eventMs)) setLastEventTime(eventMs);
          } else {
            setLastEventTime(Date.now());
          }

          scheduleRefresh([data.table]);
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

  /**
   * WIS.wsCatchUp() — manually trigger a catch-up sync.
   * Useful after the page has been in a background tab for a while.
   */
  WIS.wsCatchUp = function () {
    catchUp();
  };

  // ── Visibility change: catch up when tab becomes visible ──────────
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && isConnected) {
      // Tab just became visible — check for missed changes
      var lastMs = getLastEventTime();
      var now = Date.now();
      // Only catch up if more than 30 seconds have passed since last event
      if (lastMs && (now - lastMs) > 30000) {
        log('Tab visible after ' + Math.round((now - lastMs) / 1000) + 's — catching up');
        catchUp();
      }
    }
  });

  // ── Initialize on DOM ready ───────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
})();
