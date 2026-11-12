"""Convert internally derived real radicals to exact Z3 algebraic numerals."""
import sympy as sp
import z3

def exact_radical(value,ctx):
    expression=sp.sympify(value)
    if expression.is_Rational:return z3.RealVal(str(expression),ctx=ctx)
    if expression.is_Add:return z3.simplify(sum(exact_radical(term,ctx) for term in expression.args))
    if expression.is_Mul:
        result=z3.RealVal(1,ctx=ctx)
        for term in expression.args:result=z3.simplify(result*exact_radical(term,ctx))
        return result
    if expression.is_Pow and (expression.exp.is_Integer or expression.exp==sp.Rational(1,2)):
        return z3.simplify(exact_radical(expression.base,ctx)**z3.RealVal(str(expression.exp),ctx=ctx))
    raise ValueError('当前候选最值还不能转为精确根式')
