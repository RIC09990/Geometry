"""Finite student-facing reasons compiled into proof terms, not canned verdicts."""
from .models import Problem

class RuleMismatch(ValueError):
    pass

def length(pair):
    return f'Length {pair[0]} {pair[1]}'

def symmetric(x,y,proof):
    return f'(Eq.elim Measure ({x}) (fun v => v = ({x})) (Eq.intro Measure ({x})) ({y}) ({proof}))'

def transitive(x,y,z,first,second):
    return f'(Eq.elim Measure ({y}) (fun v => ({x}) = v) ({first}) ({z}) ({second}))'

def length_equation(target,source,proof,mode='same'):
    target_left,target_right=tuple(target[:2]),tuple(target[2:])
    source_left,source_right=tuple(source[:2]),tuple(source[2:])
    canonical=lambda pair:tuple(sorted(pair))
    same=canonical(target_left)==canonical(source_left) and canonical(target_right)==canonical(source_right)
    reverse=canonical(target_left)==canonical(source_right) and canonical(target_right)==canonical(source_left)
    if mode=='reversed' and reverse or mode=='either' and not same and reverse:
        proof=symmetric(length(source_left),length(source_right),proof)
        source_left,source_right=source_right,source_left
    elif not same or mode=='reversed':
        return None
    head=f'(Eq.intro Measure ({length(target_left)}))' if target_left==source_left else f'(length_symm {target_left[0]} {target_left[1]})'
    tail=f'(Eq.intro Measure ({length(source_right)}))' if source_right==target_right else f'(length_symm {source_right[0]} {source_right[1]})'
    middle=transitive(length(target_left),length(source_left),length(source_right),head,proof)
    return transitive(length(target_left),length(source_right),length(target_right),middle,tail)

def script(problem:Problem,reason:str,render,guaranteed_distinct):
    goal=problem.goal
    premises=[(i,r) for i,r in enumerate(problem.conditions) if r.enabled]
    if reason in {'given','line_symmetry'}:
        if reason=='line_symmetry' and goal.kind not in {'parallel','perpendicular'}:
            raise RuleMismatch('“垂直或平行换向”用于交换两条线或线段端点，请先选择垂直或平行结论。')
        for i,r in premises:
            if render(r,problem)==render(goal,problem):return f'exact h{i}.'
            if reason=='given' and goal.kind==r.kind=='equal_length':
                proof=length_equation(goal.args,r.args,f'h{i}')
                if proof:return f'exact {proof}.'
        raise RuleMismatch('所选条件中没有直接对应的已知关系，请重新选择依据，或换一个证明理由。')
    if reason=='reflexivity':
        if not render(goal,problem).startswith(('Length ','Angle ')):
            raise RuleMismatch('“同一个量”用于同一条边或同一个角，例如 AD＝AD，请调整这一步的结论。')
        return 'reflexivity.'
    if reason=='length_symmetry':
        a=goal.args
        if goal.kind!='equal_length' or a[:2]!=list(reversed(a[2:])):
            raise RuleMismatch('“线段端点换向”用于 AB＝BA 这样的结论，请检查两条线段是否只是端点顺序相反。')
        return f'exact (length_symm {a[0]} {a[1]}).'
    if reason=='equality_symmetry':
        for i,r in premises:
            if goal.kind==r.kind=='equal_length':
                proof=length_equation(goal.args,r.args,f'h{i}',mode='reversed')
                if proof:return f'exact {proof}.'
            if goal.kind==r.kind=='equal_angle' and goal.args==r.args[3:]+r.args[:3] and render(r,problem).startswith('Angle '):
                left='Angle '+' '.join(r.args[:3]);right='Angle '+' '.join(r.args[3:])
                return f'exact {symmetric(left,right,f"h{i}")}.'
        raise RuleMismatch('请选中一个相等条件，并把结论写成交换等式两边后的形式，例如由 AB＝AC 得到 AC＝AB。')
    if reason=='midpoint':
        for i,r in premises:
            if r.kind!='midpoint':continue
            middle,a,b=r.args
            if not guaranteed_distinct(problem,a,b):continue
            start=f'destruct_ands h{i} midpoint_inside midpoint_lengths.\n'
            if goal.kind=='equal_length':
                proof=length_equation(goal.args,[a,middle,middle,b],'midpoint_lengths',mode='either')
                if proof:return start+f'exact {proof}.'
            if goal.kind=='on_segment' and goal.args==[middle,a,b]:
                return start+'exact midpoint_inside.'
        raise RuleMismatch('请选中中点条件，并检查结论是否是两半线段相等，或中点在线段内部；严格内部点还需要线段不退化。')
    raise RuleMismatch('请选择一个证明理由，或打开高级模式填写证明代码。')
