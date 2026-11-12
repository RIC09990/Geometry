"""Student reason choices must produce real proofs checked by the official CLI."""
import pytest
from fastapi.testclient import TestClient
from server.models import Relation
from server import nicegeo_adapter as ng
from server.main import app
from test_nicegeo import problem,require_runtime


@pytest.mark.parametrize('reason,kind,target,given_kind,given',[
 ('given','equal_length',['A','B','A','C'],'equal_length',['A','B','A','C']),
 ('given','equal_length',['B','A','C','A'],'equal_length',['A','B','A','C']),
 ('reflexivity','equal_length',['A','D','A','D'],None,None),
 ('length_symmetry','equal_length',['A','B','B','A'],None,None),
 ('equality_symmetry','equal_length',['A','C','A','B'],'equal_length',['A','B','A','C']),
 ('equality_symmetry','equal_length',['C','A','B','A'],'equal_length',['A','B','A','C']),
 ('midpoint','equal_length',['B','D','D','C'],'midpoint',['D','B','C']),
 ('midpoint','equal_length',['C','D','D','B'],'midpoint',['D','B','C']),
 ('midpoint','on_segment',['D','B','C'],'midpoint',['D','B','C']),
 ('line_symmetry','perpendicular',['B','C','D','A'],'perpendicular',['A','D','B','C']),
 ('line_symmetry','parallel',['D','C','B','A'],'parallel',['A','B','C','D']),
])
def test_choice_is_compiled_into_a_real_kernel_checked_proof(reason,kind,target,given_kind,given):
 require_runtime();p=problem();p.goal=Relation(id='goal',kind=kind,args=target)
 if given:p.conditions=[Relation(id='given',kind=given_kind,args=given)]
 result=ng.check(p,reason=reason)
 assert result['status']=='verified',result
 assert 'Valid proofs!' in result['raw']


def test_wrong_reason_does_not_turn_a_true_conclusion_into_a_valid_student_proof():
 require_runtime();p=problem()
 p.conditions=[Relation(id='given',kind='equal_length',args=['A','B','A','C'])]
 statement=Relation(id='step',kind='equal_length',args=['A','B','A','C'])
 response=TestClient(app).post('/api/check-step',json={'problem':p.model_dump(),'statement':statement.model_dump(),'premises':['given'],'reason':'reflexivity'})
 assert response.status_code==200
 data=response.json()
 assert data['status']=='rejected' and data['constraintCheck']['outcome']=='proven'


def test_common_reason_requires_the_selected_premise_and_is_not_a_canned_success():
 require_runtime();p=problem();p.goal.args=['A','B','A','C']
 result=ng.check(p,reason='given')
 assert result['status']=='cannot_check'
 assert 'source' not in result


def test_advanced_original_script_input_is_still_accepted():
 require_runtime()
 assert ng.check(problem(),'reflexivity.','custom')['status']=='verified'
