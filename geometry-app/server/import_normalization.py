"""Normalize provider spellings, preserving every non-formalized statement as text."""
import copy
import json
from .models import KINDS
from .spatial_conditions import spatial_statement

ALIASES={'angle':'fixed_angle','segment_equal':'equal_length','equal_segments':'equal_length',
         'point_on_segment':'on_segment','on_line_segment':'on_segment','between':'on_segment',
         'parallel_lines':'parallel','perpendicular_lines':'perpendicular','distance':'fixed_length',
         'angle_measure':'fixed_angle','angle_bisector':'angle_bisector','similar':'similar_triangles',
         'minimum':'minimize','maximise':'maximize','minimise':'minimize'}
ALIASES.update({'point_in_triangle':'inside_triangle','in_triangle':'inside_triangle','interior_point':'inside_triangle',
                'in_circle':'inside_circle','exterior_circle':'outside_circle','same_side_of_line':'same_side','opposite_sides':'opposite_side'})

def normalize_problem(raw,recognized_text='',notices=()):
    p=copy.deepcopy(raw)
    domain=p.setdefault('nondegenerate',{'distinct':False,'triangles':[]})
    if not isinstance(domain,dict):domain={'distinct':False,'triangles':[]};p['nondegenerate']=domain
    domain.setdefault('triangles',[]);domain.setdefault('distinct',False)
    ids={q.get('id') for q in p.get('points',[]) if isinstance(q,dict)}
    conditions=[]
    def normalized(r,is_goal=False):
        r=copy.deepcopy(r)
        if not isinstance(r,dict):r={'kind':'free_text','description':str(r)}
        r.setdefault('kind',r.pop('type','free_text'));r.setdefault('args',r.pop('points',[]))
        kind=str(r['kind']).lower().replace('-','_')
        if kind in ('nondegenerate','non_collinear','noncollinear','ncoll') and not is_goal and len(r['args'])==3 and set(r['args'])<=ids:
            if r['args'] not in domain['triangles']:domain['triangles'].append(r['args'])
            return None
        kind=ALIASES.get(kind,kind)
        if kind=='fixed_angle' and r.get('value') is None and is_goal:kind='angle_value'
        if kind not in KINDS:
            description=r.get('description') or r.get('statement') or r.get('text') or r.get('expression')
            if not description:description=json.dumps(r,ensure_ascii=False,separators=(',',':'))
            r={'kind':'free_text','description':description,'args':[a for a in r.get('args',[]) if a in ids]}
            kind='free_text'
        r['kind']=kind
        if kind=='free_text':
            r['description']=r.get('description') or r.get('statement') or r.get('text') or r.get('expression') or recognized_text
            r={k:v for k,v in r.items() if k in ('id','kind','args','description','enabled','toggleable')}
            spatial=spatial_statement(r['description'])
            if spatial and set(spatial['args'])<=ids:r.update(spatial)
        r.setdefault('id','goal' if is_goal else 'condition-'+str(len(conditions)+1))
        r.setdefault('enabled',True);r.setdefault('toggleable',not is_goal)
        return r
    for raw_relation in p.get('conditions',[]):
        r=normalized(raw_relation)
        if r:conditions.append(r)
    p['conditions']=conditions
    if p.get('goal') is not None:p['goal']=normalized(p['goal'],True)
    for notice in notices:
        if notice and not any(r.get('description')==notice for r in conditions):
            spatial=spatial_statement(notice)
            if spatial and set(spatial['args'])<=ids:
                if not any(r['kind']==spatial['kind'] and r['args']==spatial['args'] for r in conditions):
                    conditions.append({'id':'text-'+str(len(conditions)+1),**spatial,'description':str(notice),'enabled':True,'toggleable':True})
            else:conditions.append({'id':'text-'+str(len(conditions)+1),'kind':'free_text','args':[],
                                    'description':str(notice),'enabled':True,'toggleable':True})
    p['sourceText']=recognized_text
    return p
