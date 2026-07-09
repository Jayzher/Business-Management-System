/*
 * Floating Unit Calculator (bottom-right, minimizable).
 * Client-side only — uses the fixed, physics-based conversion table below,
 * which mirrors catalog/standard_units.py:STANDARD_CONVERSIONS /
 * TEMPERATURE_CONVERSIONS. Only categories with a universal conversion
 * factor are included (length, mass, volume, area, time, speed,
 * temperature). Business-defined units (pcs, roll, sheet, box, pack,
 * etc.) vary per item and are intentionally left out — those are handled
 * per-item under Catalog -> Unit Conversions.
 *
 * Select2 is initialized lazily, the first time the panel is actually
 * opened (display != none). Initializing Select2 on a hidden element
 * makes it measure zero width and permanently mis-position its dropdown —
 * that's why these selects carry the `no-select2` class, opting them out
 * of the global wisInitSelect2() auto-init that runs on page load.
 */
(function ($) {
  var CATEGORIES = {
    length: {
      label: 'Length', icon: 'fa-ruler',
      units: [
        ['um', 'Micrometer'], ['mm', 'Millimeter'], ['cm', 'Centimeter'],
        ['m', 'Meter'], ['km', 'Kilometer'], ['mil', 'Mil (thou)'],
        ['in', 'Inch'], ['ft', 'Foot'], ['yd', 'Yard'], ['mi', 'Mile'],
        ['nmi', 'Nautical mile'],
      ],
      factors: {
        um: 0.000001, mm: 0.001, cm: 0.01, m: 1, km: 1000,
        mil: 0.0000254, in: 0.0254, ft: 0.3048, yd: 0.9144,
        mi: 1609.344, nmi: 1852,
      },
    },
    mass: {
      label: 'Mass', icon: 'fa-weight-hanging',
      units: [
        ['mg', 'Milligram'], ['g', 'Gram'], ['kg', 'Kilogram'],
        ['t', 'Metric Ton'], ['oz', 'Ounce'], ['lb', 'Pound'],
        ['st', 'Stone'],
      ],
      factors: {
        mg: 0.000001, g: 0.001, kg: 1, t: 1000,
        oz: 0.0283495, lb: 0.4535924, st: 6.35029,
      },
    },
    volume: {
      label: 'Volume', icon: 'fa-flask',
      units: [
        ['mL', 'Milliliter'], ['L', 'Liter'], ['kL', 'Kiloliter'],
        ['in3', 'Cubic inch'], ['ft3', 'Cubic foot'], ['yd3', 'Cubic yard'],
        ['m3', 'Cubic meter'], ['floz', 'Fluid ounce'], ['cup', 'Cup'],
        ['pt', 'Pint'], ['qt', 'Quart'], ['gal', 'Gallon'],
      ],
      factors: {
        mL: 0.001, L: 1, kL: 1000,
        in3: 0.016387064, ft3: 28.316846592, yd3: 764.554857984, m3: 1000,
        floz: 0.0295735, cup: 0.2365882, pt: 0.473176, qt: 0.946353, gal: 3.785412,
      },
    },
    area: {
      label: 'Area', icon: 'fa-vector-square',
      units: [
        ['mm2', 'Square millimeter'], ['cm2', 'Square centimeter'],
        ['in2', 'Square inch'], ['ft2', 'Square foot'], ['yd2', 'Square yard'],
        ['m2', 'Square meter'], ['ha', 'Hectare'], ['acre', 'Acre'],
        ['km2', 'Square kilometer'],
      ],
      factors: {
        mm2: 0.000001, cm2: 0.0001, in2: 0.00064516, ft2: 0.09290304,
        yd2: 0.83612736, m2: 1, ha: 10000, acre: 4046.8564, km2: 1000000,
      },
    },
    time: {
      label: 'Time', icon: 'fa-clock',
      units: [
        ['s', 'Second'], ['min', 'Minute'], ['hr', 'Hour'],
        ['day', 'Day'], ['week', 'Week'],
      ],
      factors: { s: 1, min: 60, hr: 3600, day: 86400, week: 604800 },
    },
    speed: {
      label: 'Speed', icon: 'fa-gauge-high',
      units: [
        ['m/s', 'Meters/sec'], ['km/h', 'Km/hour'], ['mph', 'Miles/hour'],
        ['ft/s', 'Feet/sec'], ['knot', 'Knot'],
      ],
      factors: {
        'm/s': 1, 'km/h': 0.2777778, mph: 0.44704, 'ft/s': 0.3048, knot: 0.5144444,
      },
    },
    temperature: {
      label: 'Temp', icon: 'fa-temperature-half',
      units: [['C', 'Celsius'], ['F', 'Fahrenheit'], ['K', 'Kelvin']],
      formula: true,
      toBase: {
        C: function (v) { return v; },
        F: function (v) { return (v - 32) * 5 / 9; },
        K: function (v) { return v - 273.15; },
      },
      fromBase: {
        C: function (v) { return v; },
        F: function (v) { return v * 9 / 5 + 32; },
        K: function (v) { return v + 273.15; },
      },
    },
  };

  var CATEGORY_ORDER = ['length', 'mass', 'volume', 'area', 'time', 'speed', 'temperature'];
  var OPEN_KEY = 'wis-unit-calc-open';
  var HISTORY_KEY = 'wis-unit-calc-history';
  var HISTORY_MAX = 5;

  var select2Ready = false;
  var currentCategory = 'length';

  function formatOption(pair) {
    return '<option value="' + pair[0] + '" title="' + pair[1] + '">' + pair[0] + ' (' + pair[1] + ')</option>';
  }

  function formatNumber(n) {
    var abs = Math.abs(n);
    if (abs >= 1000 || (abs < 0.0001 && n !== 0)) return n.toExponential(4);
    var rounded = Math.round(n * 1e6) / 1e6;
    return rounded.toLocaleString('en-US', { maximumFractionDigits: 6 });
  }

  function buildRail() {
    var $rail = $('#wis-unit-calc-rail');
    var html = '';
    CATEGORY_ORDER.forEach(function (key) {
      var cat = CATEGORIES[key];
      html += '<button type="button" class="wis-unit-calc-rail-btn' + (key === currentCategory ? ' active' : '') +
        '" data-category="' + key + '" title="' + cat.label + '">' +
        '<i class="fas ' + cat.icon + '"></i><span>' + cat.label + '</span></button>';
    });
    $rail.html(html);
  }

  function populateUnitSelects(categoryKey, $from, $to, preferFrom, preferTo) {
    var units = CATEGORIES[categoryKey].units;
    var html = units.map(formatOption).join('');
    $from.html(html);
    $to.html(html);
    var fromVal = units.some(function (p) { return p[0] === preferFrom; }) ? preferFrom : units[0][0];
    var toVal = units.some(function (p) { return p[0] === preferTo; }) ? preferTo : (units.length > 1 ? units[1][0] : units[0][0]);
    $from.val(fromVal);
    $to.val(toVal);
  }

  function getHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch (e) { return []; }
  }

  function pushHistory(entry) {
    var list = getHistory();
    list.unshift(entry);
    list = list.slice(0, HISTORY_MAX);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(list)); } catch (e) { /* ignore */ }
    renderHistory();
  }

  function renderHistory() {
    var list = getHistory();
    var $wrap = $('#wis-unit-calc-history');
    var $list = $('#wis-unit-calc-history-list');
    if (!list.length) { $wrap.hide(); return; }
    $wrap.show();
    $list.html(list.map(function (h, i) {
      return '<button type="button" class="wis-unit-calc-history-item" data-index="' + i + '">' +
        h.value + ' ' + h.from + ' = ' + h.result + ' ' + h.to + '</button>';
    }).join(''));
  }

  function compute() {
    var category = CATEGORIES[currentCategory];
    var fromAbbr = $('#wis-unit-calc-from').val();
    var toAbbr = $('#wis-unit-calc-to').val();
    var rawValue = parseFloat($('#wis-unit-calc-value').val());
    var $value = $('#wis-unit-calc-result-value');
    var $sub = $('#wis-unit-calc-result-sub');

    if (!category || isNaN(rawValue)) {
      $value.text('—');
      $sub.text('');
      return null;
    }

    var result;
    if (category.formula) {
      if (!category.toBase[fromAbbr] || !category.fromBase[toAbbr]) {
        $value.text('—'); $sub.text(''); return null;
      }
      result = category.fromBase[toAbbr](category.toBase[fromAbbr](rawValue));
    } else {
      var factors = category.factors;
      if (!(fromAbbr in factors) || !(toAbbr in factors)) {
        $value.text('—'); $sub.text(''); return null;
      }
      result = (rawValue * factors[fromAbbr]) / factors[toAbbr];
    }

    var formatted = formatNumber(result);
    $value.text(formatted + ' ' + toAbbr);
    $sub.text(rawValue + ' ' + fromAbbr + ' = ' + formatted + ' ' + toAbbr);

    return { value: rawValue, from: fromAbbr, to: toAbbr, result: formatted, category: currentCategory };
  }

  function initSelect2Once() {
    if (select2Ready || !$.fn.select2) return;
    select2Ready = true;

    var $panel = $('#wis-unit-calc-panel');
    ['#wis-unit-calc-from', '#wis-unit-calc-to'].forEach(function (sel) {
      $(sel).select2({
        theme: 'bootstrap-5',
        width: '100%',
        minimumResultsForSearch: 0,
        dropdownParent: $panel,
        dropdownCssClass: 'wis-unit-calc-dropdown',
        containerCssClass: 'wis-unit-calc-select',
      });
    });
    $('#wis-unit-calc-from, #wis-unit-calc-to').on('change', function () {
      var entry = compute();
      if (entry) pushHistory(entry);
    });
  }

  function switchCategory(key, preferFrom, preferTo) {
    currentCategory = key;
    $('.wis-unit-calc-rail-btn').removeClass('active');
    $('.wis-unit-calc-rail-btn[data-category="' + key + '"]').addClass('active');

    var $from = $('#wis-unit-calc-from');
    var $to = $('#wis-unit-calc-to');
    populateUnitSelects(key, $from, $to, preferFrom, preferTo);
    if (select2Ready) {
      $from.trigger('change.select2');
      $to.trigger('change.select2');
    }
    compute();
  }

  function setOpen(open) {
    var $root = $('#wis-unit-calc');
    $root.toggleClass('open', open);
    $('#wis-unit-calc-toggle').attr('aria-expanded', open ? 'true' : 'false');
    try { localStorage.setItem(OPEN_KEY, open ? '1' : '0'); } catch (e) { /* ignore */ }
    if (open) {
      // Panel is now visible — safe to size Select2 correctly (hidden elements measure zero-width).
      initSelect2Once();
    }
  }

  function isOpen() {
    return $('#wis-unit-calc').hasClass('open');
  }

  $(function () {
    var $root = $('#wis-unit-calc');
    if (!$root.length) return;

    buildRail();
    var $from = $('#wis-unit-calc-from');
    var $to = $('#wis-unit-calc-to');
    populateUnitSelects(currentCategory, $from, $to);
    compute();
    renderHistory();

    $('#wis-unit-calc-rail').on('click', '.wis-unit-calc-rail-btn', function () {
      switchCategory($(this).data('category'));
    });

    $('#wis-unit-calc-value').on('input', compute);
    $('#wis-unit-calc-value').on('change', function () {
      var entry = compute();
      if (entry) pushHistory(entry);
    });

    $('#wis-unit-calc-swap').on('click', function () {
      var f = $from.val(), t = $to.val();
      $from.val(t);
      $to.val(f);
      if (select2Ready) {
        $from.trigger('change.select2');
        $to.trigger('change.select2');
      }
      var entry = compute();
      if (entry) pushHistory(entry);
    });

    $('#wis-unit-calc-copy').on('click', function () {
      var text = $('#wis-unit-calc-result-value').text();
      if (!text || text === '—') return;
      var entry = compute();
      if (entry) pushHistory(entry);
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () {
          if (window.WIS && typeof WIS.toast === 'function') WIS.toast('Copied "' + text + '" to clipboard.', 'success');
        }).catch(function () { /* ignore */ });
      }
    });

    $('#wis-unit-calc-history-list').on('click', '.wis-unit-calc-history-item', function () {
      var list = getHistory();
      var entry = list[$(this).data('index')];
      if (!entry) return;
      switchCategory(entry.category, entry.from, entry.to);
      $('#wis-unit-calc-value').val(entry.value);
      if (select2Ready) {
        $from.trigger('change.select2');
        $to.trigger('change.select2');
      }
      compute();
    });

    $('#wis-unit-calc-toggle').on('click', function () {
      setOpen(!isOpen());
    });
    $('#wis-unit-calc-close').on('click', function (e) {
      e.stopPropagation();
      setOpen(false);
    });

    $(document).on('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) setOpen(false);
    });
    $(document).on('mousedown', function (e) {
      if (!isOpen()) return;
      if ($(e.target).closest('#wis-unit-calc, .select2-container').length) return;
      setOpen(false);
    });

    var wasOpen = false;
    try { wasOpen = localStorage.getItem(OPEN_KEY) === '1'; } catch (e) { /* ignore */ }
    if (wasOpen) setOpen(true);
  });
})(jQuery);
