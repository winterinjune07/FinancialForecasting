"""
paycheck.py -- net pay from one biweekly gross paycheck.

Tax year 2026. Single filer, W-2 wages, standard deduction, resident of
Cincinnati, OH. Annualizes the check (x26), computes annual tax, divides back.

Usage:
    from paycheck import netPay, breakdown
    netPay(1200.00)       # -> float
    breakdown(1200.00)    # -> dict of per-check amounts
"""

PAY_PERIODS = 26  # biweekly

# ---- Federal (2026, single) ----
FED_STD_DEDUCTION = 16100
FED_BRACKETS = [  # (upper limit of taxable income, rate)
    (12400, 0.10),
    (50400, 0.12),
    (105700, 0.22),
    (201775, 0.24),
    (256225, 0.32),
    (640600, 0.35),
    (float('inf'), 0.37),
]

# ---- FICA ----
SS_RATE, SS_WAGE_BASE = 0.062, 184500
MEDICARE_RATE = 0.0145
ADDL_MEDICARE_RATE, ADDL_MEDICARE_THRESHOLD = 0.009, 200000

# ---- Ohio (2026): $0 up to threshold, then base + rate on the excess ----
OHIO_ZERO_BRACKET = 26050
OHIO_BASE, OHIO_RATE = 332.00, 0.0275

# ---- Cincinnati earnings tax (on gross) ----
CINCINNATI_RATE = 0.018


def _federal(annual):
    taxable = max(0.0, annual - FED_STD_DEDUCTION)
    tax, lower = 0.0, 0.0
    for upper, rate in FED_BRACKETS:
        if taxable > lower:
            tax += (min(taxable, upper) - lower) * rate
        lower = upper
    return tax


def _fica(annual):
    ss = min(annual, SS_WAGE_BASE) * SS_RATE
    medicare = annual * MEDICARE_RATE
    addl = max(0.0, annual - ADDL_MEDICARE_THRESHOLD) * ADDL_MEDICARE_RATE
    return ss + medicare + addl


def _ohio(annual):
    if annual <= OHIO_ZERO_BRACKET:
        return 0.0
    return OHIO_BASE + OHIO_RATE * (annual - OHIO_ZERO_BRACKET)


def _cincinnati(annual):
    return annual * CINCINNATI_RATE


def breakdown(gross):
    """Per-check amounts for one biweekly gross paycheck."""
    gross = float(gross)
    if gross < 0:
        raise ValueError("gross must be non-negative")
    annual = gross * PAY_PERIODS
    parts = {
        'federal': _federal(annual) / PAY_PERIODS,
        'fica': _fica(annual) / PAY_PERIODS,
        'ohio': _ohio(annual) / PAY_PERIODS,
        'cincinnati': _cincinnati(annual) / PAY_PERIODS,
    }
    parts['total_tax'] = sum(parts.values())
    parts['gross'] = gross
    parts['net'] = gross - parts['total_tax']
    return {k: round(v, 2) for k, v in parts.items()}


def netPay(gross):
    """Net pay for one biweekly gross paycheck."""
    return breakdown(gross)['net']


def breakdownMany(grosses):
    """
    List of biweekly gross checks -> per-check breakdowns plus totals.

    Annual income = sum(grosses) if the list covers a full year (>= 26 checks).
    Otherwise it is projected as mean(grosses) * 26, i.e. it assumes the
    remaining checks average the same as the ones given.
    Each check's tax = gross * (annual tax / annual income), so the per-check
    taxes sum to the annual tax when the list is a full year.
    """
    grosses = [float(g) for g in grosses]
    if not grosses:
        raise ValueError("grosses is empty")
    if min(grosses) < 0:
        raise ValueError("gross must be non-negative")

    projected = len(grosses) < PAY_PERIODS
    annual = (sum(grosses) / len(grosses)) * PAY_PERIODS if projected else sum(grosses)

    if annual == 0:
        rates = {'federal': 0.0, 'fica': 0.0, 'ohio': 0.0, 'cincinnati': 0.0}
    else:
        rates = {
            'federal': _federal(annual) / annual,
            'fica': _fica(annual) / annual,
            'ohio': _ohio(annual) / annual,
            'cincinnati': _cincinnati(annual) / annual,
        }

    checks = []
    for g in grosses:
        c = {k: g * r for k, r in rates.items()}
        c['total_tax'] = sum(c.values())
        c['gross'] = g
        c['net'] = g - c['total_tax']
        checks.append({k: round(v, 2) for k, v in c.items()})

    totals = {k: round(sum(c[k] for c in checks), 2) for k in checks[0]}
    return {
        'checks': checks,
        'totals': totals,
        'annual_income_used': round(annual, 2),
        'projected': projected,
    }