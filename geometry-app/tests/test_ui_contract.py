import json
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from server.main import app

def test_builder_object_identifiers_roundtrip_through_validation():
    c=json.loads((Path(__file__).resolve().parents[1]/'data/cases.json').read_text(encoding='utf-8'))[0]
    p={k:v for k,v in c.items() if k not in ['description','tag']}
    for segment in p['segments']:segment['id']='segment-'+str(uuid4())
    p['circles']=[{'id':'circle-'+str(uuid4()),'center':'A','through':'B'}]
    response=TestClient(app).post('/api/validate',json={'problem':p})
    assert response.status_code==200,response.text
    assert response.json()['status']=='sat'
