"""
Real-world (physics-based) unit conversion dictionary.

Unlike catalog.models.UnitConversion (which stores business-specific,
per-item factors like "1 roll = 30 m" that vary per product), the factors
below are universal and never change — 1 meter is always 1000 millimeters.

Only categories with a fixed physical definition are included here: length,
mass, volume, area, time, speed, and temperature. The remaining
UnitCategory values on the Unit model (quantity, material, logistics) are
inherently business-defined (a "roll", "sheet", "box" or "pack" has no
fixed size) and must stay as item-specific UnitConversion records — they
are intentionally not represented here.

Most categories are multiplicative: each inner dict maps a unit
abbreviation to how many of that unit make up one "base unit" for the
category (the base unit itself maps to 1), and converting is just
value * from_factor / to_factor.

Temperature is the one non-multiplicative case (Celsius/Fahrenheit have an
offset, not just a scale), so it's handled separately via explicit
to-base/from-base formulas in TEMPERATURE_CONVERSIONS.
"""
from decimal import Decimal


STANDARD_CONVERSIONS = {
    'length': {
        'base_unit': 'm',
        'factors': {
            'um': Decimal('0.000001'),
            'mm': Decimal('0.001'),
            'cm': Decimal('0.01'),
            'm': Decimal('1'),
            'km': Decimal('1000'),
            'mil': Decimal('0.0000254'),
            'in': Decimal('0.0254'),
            'ft': Decimal('0.3048'),
            'yd': Decimal('0.9144'),
            'mi': Decimal('1609.344'),
            'nmi': Decimal('1852'),
        },
    },
    'mass': {
        'base_unit': 'kg',
        'factors': {
            'mg': Decimal('0.000001'),
            'g': Decimal('0.001'),
            'kg': Decimal('1'),
            't': Decimal('1000'),
            'oz': Decimal('0.0283495'),
            'lb': Decimal('0.4535924'),
            'st': Decimal('6.35029'),
        },
    },
    'volume': {
        'base_unit': 'L',
        'factors': {
            'mL': Decimal('0.001'),
            'L': Decimal('1'),
            'kL': Decimal('1000'),
            'in3': Decimal('0.016387064'),
            'ft3': Decimal('28.316846592'),
            'yd3': Decimal('764.554857984'),
            'm3': Decimal('1000'),
            'floz': Decimal('0.0295735'),
            'cup': Decimal('0.2365882'),
            'pt': Decimal('0.473176'),
            'qt': Decimal('0.946353'),
            'gal': Decimal('3.785412'),
        },
    },
    'area': {
        'base_unit': 'm2',
        'factors': {
            'mm2': Decimal('0.000001'),
            'cm2': Decimal('0.0001'),
            'in2': Decimal('0.00064516'),
            'ft2': Decimal('0.09290304'),
            'yd2': Decimal('0.83612736'),
            'm2': Decimal('1'),
            'ha': Decimal('10000'),
            'acre': Decimal('4046.8564'),
            'km2': Decimal('1000000'),
        },
    },
    'time': {
        'base_unit': 's',
        'factors': {
            's': Decimal('1'),
            'min': Decimal('60'),
            'hr': Decimal('3600'),
            'day': Decimal('86400'),
            'week': Decimal('604800'),
        },
    },
    'speed': {
        'base_unit': 'm/s',
        'factors': {
            'm/s': Decimal('1'),
            'km/h': Decimal('0.2777778'),
            'mph': Decimal('0.44704'),
            'ft/s': Decimal('0.3048'),
            'knot': Decimal('0.5144444'),
        },
    },
}


def _c_to_c(v):
    return v


def _f_to_c(v):
    return (v - 32) * Decimal('5') / Decimal('9')


def _k_to_c(v):
    return v - Decimal('273.15')


def _c_to_f(v):
    return v * Decimal('9') / Decimal('5') + 32


def _c_to_k(v):
    return v + Decimal('273.15')


# Formula-based (non-multiplicative) conversions: unit -> Celsius, and
# Celsius -> unit. Temperature can't be expressed as a simple factor
# because Celsius/Fahrenheit/Kelvin scales don't share a zero point.
TEMPERATURE_CONVERSIONS = {
    'base_unit': 'C',
    'to_base': {
        'C': _c_to_c,
        'F': _f_to_c,
        'K': _k_to_c,
    },
    'from_base': {
        'C': _c_to_c,
        'F': _c_to_f,
        'K': _c_to_k,
    },
}


def convert_temperature(value, from_abbr, to_abbr):
    """Convert *value* between 'C', 'F', 'K' using the offset formulas
    above. Returns a Decimal, or None if either abbreviation is unknown."""
    to_base = TEMPERATURE_CONVERSIONS['to_base']
    from_base = TEMPERATURE_CONVERSIONS['from_base']
    if from_abbr not in to_base or to_abbr not in from_base:
        return None
    value = Decimal(str(value))
    celsius = to_base[from_abbr](value)
    return from_base[to_abbr](celsius)


def convert_standard(value, from_abbr, to_abbr):
    """Convert *value* from unit *from_abbr* to unit *to_abbr* using the
    fixed physical dictionary above (including temperature). Both units
    must belong to the same category. Returns a Decimal, or None if either
    unit isn't recognized or they belong to different categories.
    """
    if from_abbr in TEMPERATURE_CONVERSIONS['to_base'] and to_abbr in TEMPERATURE_CONVERSIONS['from_base']:
        return convert_temperature(value, from_abbr, to_abbr)

    value = Decimal(str(value))
    for category, spec in STANDARD_CONVERSIONS.items():
        factors = spec['factors']
        if from_abbr in factors and to_abbr in factors:
            base_value = value * factors[from_abbr]
            return base_value / factors[to_abbr]
    return None


def category_for_unit(abbr):
    """Return the standard-conversions category name containing unit
    abbreviation *abbr*, or None if it isn't part of the fixed dictionary
    (e.g. business-defined units like pcs, roll, sheet, box)."""
    if abbr in TEMPERATURE_CONVERSIONS['to_base']:
        return 'temperature'
    for category, spec in STANDARD_CONVERSIONS.items():
        if abbr in spec['factors']:
            return category
    return None
