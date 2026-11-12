"""Exact algebraic cosines for angle constraints (never rounded trig constants)."""
from functools import lru_cache
from fractions import Fraction
import sympy as s
import z3


def supported_angle(value):
    degree = s.Rational(str(value))
    if not 0 < degree < 180:
        raise ValueError('角度必须大于 0° 且小于 180°')
    order = (degree / 360).q
    if s.totient(order) > 96:
        raise ValueError('这个角度的精确计算暂时过于复杂，请使用整数度或常见分数角度')
    return degree


@lru_cache(maxsize=128)
def cosine_data(value):
    degree = supported_angle(value)
    cosine = s.cos(s.pi * degree / 180)
    if cosine.is_Rational:
        return str(cosine), None, None
    x = s.Symbol('x')
    poly = s.Poly(s.minpoly(cosine, x), x)
    numeric = cosine.evalf(80)
    intervals = poly.intervals(eps=s.Rational(1, 10**30))
    for (lo, hi), multiplicity in intervals:
        if multiplicity == 1 and lo.evalf(80) <= numeric <= hi.evalf(80):
            return None, tuple(str(v) for v in poly.all_coeffs()), (str(lo), str(hi))
    raise ValueError('无法确定该角度的精确代数根')


def cosine_constant(value, ctx):
    rational, coefficients, interval = cosine_data(value)
    if rational is not None:
        return z3.RealVal(rational, ctx=ctx)
    # A separate solver isolates the real algebraic value once. Returning the
    # algebraic numeral avoids free auxiliary variables inside a negated goal.
    x = z3.Real('angle_cosine', ctx=ctx)
    polynomial = z3.RealVal(0, ctx=ctx)
    for coefficient in coefficients:
        polynomial = polynomial*x + z3.RealVal(coefficient, ctx=ctx)
    solver = z3.Tactic('qfnra-nlsat', ctx=ctx).solver()
    solver.set(timeout=2000)
    solver.add(polynomial == 0, x >= z3.RealVal(interval[0], ctx=ctx), x <= z3.RealVal(interval[1], ctx=ctx))
    if solver.check() != z3.sat:
        raise ValueError('角度常量的精确计算未完成')
    return solver.model().eval(x)


def display_number(value):
    if z3.is_rational_value(value):
        return float(Fraction(value.numerator_as_long(), value.denominator_as_long()))
    return float(value.as_decimal(18).rstrip('?'))
