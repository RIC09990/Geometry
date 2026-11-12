"""The shipped catalogue must be reproducible and valid before any layout repair."""
import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import sympy as s

from server.algebra import cross, holds, length2, vector
from server.models import Problem

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = json.loads((ROOT / 'data' / 'cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('entry', CATALOGUE, ids=lambda entry: entry['id'])
def test_shipped_coordinates_satisfy_every_premise_goal_and_domain_exactly(entry):
    problem = Problem.model_validate({k: v for k, v in entry.items() if k not in {'tag', 'description'}})
    coordinates = {point.id: (s.Rational(str(point.x)), s.Rational(str(point.y))) for point in problem.points}
    for relation in [*problem.conditions, problem.goal]:
        if relation.enabled:
            assert holds(coordinates, relation), (problem.id, relation.id)
    if problem.nondegenerate.distinct:
        assert all(length2(coordinates, a, b) > 0 for a, b in itertools.combinations(coordinates, 2))
    for a, b, c in problem.nondegenerate.triangles:
        assert cross(vector(coordinates, a, b), vector(coordinates, a, c)) != 0
    # The stored sketch itself must have usable objects, without relying on a
    # later solver pass to repair a collapsed edge or circle.
    assert len({segment.id for segment in problem.segments}) == len(problem.segments)
    for segment in problem.segments:
        assert length2(coordinates, *segment.points) > 0
    for circle in problem.circles:
        assert length2(coordinates, circle.center, circle.through) > 0


def test_catalogue_ids_are_unique_and_generated_source_matches_from_another_directory(tmp_path):
    assert len({entry['id'] for entry in CATALOGUE}) == len(CATALOGUE)
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to compare the catalogue generation source')
    result = subprocess.run(
        [node, str(ROOT / 'scripts' / 'create-cases.mjs'), '--check'],
        cwd=tmp_path, text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert f'{len(CATALOGUE)} catalogue entries match' in result.stdout
    assert not (tmp_path / 'data').exists(), 'Checking from another directory must not create a second catalogue'


def test_importing_the_generator_is_read_only_and_explicit_output_is_reproducible(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to compare the catalogue generation source')
    destination = tmp_path / 'export' / 'catalogue.json'
    source = ROOT / 'scripts' / 'create-cases.mjs'
    program = ('import {cases,writeCases} from ' + json.dumps(source.as_uri()) + ';'
               'writeCases(' + json.dumps(str(destination)) + ');'
               'process.stdout.write(JSON.stringify(cases));')
    result = subprocess.run([node, '--input-type=module', '-e', program], cwd=tmp_path,
                            text=True, encoding='utf-8', capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == CATALOGUE
    assert json.loads(destination.read_text(encoding='utf-8')) == CATALOGUE
    assert not (tmp_path / 'data').exists()
