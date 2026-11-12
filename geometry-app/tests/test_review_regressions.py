"""Regression cases found while reviewing proof provenance and API input."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.constraints import ConstraintSystem
from server.main import app
from server.models import Point, Problem, Relation
from server.proofs import newclid


def catalogue_problem():
    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "cases.json").read_text(
            encoding="utf-8"
        )
    )[0]
    return Problem.model_validate(
        {key: value for key, value in raw.items() if key not in {"description", "tag"}}
    )


def test_collinearity_trace_is_not_a_proof_of_strict_segment_membership():
    problem = catalogue_problem()
    problem.conditions = [
        Relation(id="line", kind="collinear", args=["D", "B", "C"]),
        Relation(id="mid", kind="midpoint", args=["D", "B", "C"]),
    ]
    problem.goal = Relation(id="goal", kind="on_segment", args=["D", "B", "C"])

    # The original goal is true, independently of Newclid's supported language.
    assert ConstraintSystem(problem).analyze()["outcome"] == "proven"
    search = newclid(problem)
    assert search["status"] != "found", search

    # Collinearity alone permits D beyond an endpoint; a coll trace must not be
    # labelled a proof whose original strict goal depends only on "line".
    problem.conditions[1].enabled = False
    result = ConstraintSystem(problem).analyze()
    assert result["outcome"] == "counterexample"
    assert result["counterexample"]["verified"]


@pytest.mark.parametrize("condition_id", ["domain", "nc-C0", "t-sides"])
def test_condition_ids_cannot_alias_internal_proof_nodes(condition_id):
    payload = catalogue_problem().model_dump()
    payload["conditions"][0]["id"] = condition_id
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/validate", json={"problem": payload}
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "previous",
    [
        {"steps": [{}]},
        {"steps": [], "assumptionIds": [{}]},
        {"steps": [], "assumptionNodes": [{"id": [], "premises": []}]},
    ],
)
def test_malformed_previous_proof_is_rejected_before_dependency_traversal(previous):
    problem = catalogue_problem()
    problem.conditions.append(
        Relation(id="contradiction", kind="collinear", args=["A", "B", "C"])
    )
    # Keep this input check independent of the cost or outcome of proof search.
    assert ConstraintSystem(problem).analyze()["outcome"] == "inconsistent"
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/analyze", json={"problem": problem.model_dump(), "previous": [previous]}
    )
    assert response.status_code == 422, response.text


def test_accepted_layout_can_be_submitted_to_the_api_again():
    problem = catalogue_problem()
    problem.conditions = [
        Relation(id="mid", kind="midpoint", args=["D", "B", "C"])
    ]
    result = ConstraintSystem(problem, normalize=False).layout(
        Point(id="D", x=10000, y=10000)
    )
    if result["status"] == "sat":
        payload = problem.model_dump()
        payload["points"] = result["points"]
        # Accepted display coordinates must obey the Point schema; otherwise
        # the next analyze/validate call rejects the server's own layout.
        Problem.model_validate(payload)


def test_circle_trace_retains_any_needed_nonzero_radius_support():
    problem = catalogue_problem()
    problem.points = [
        Point(id=name, x=x, y=y)
        for name, (x, y) in {
            "A": (0, 2),
            "B": (-2, 0),
            "C": (2, 0),
            "D": (-1, 0),
            "E": (-1, 1),
        }.items()
    ]
    problem.nondegenerate.distinct = False
    problem.conditions = [
        Relation(id="length", kind="equal_length", args=["E", "D", "B", "D"]),
        Relation(id="radius", kind="parallel", args=["D", "B", "B", "C"]),
    ]
    problem.goal = Relation(id="goal", kind="on_circle", args=["E", "D", "B"])

    assert ConstraintSystem(problem).analyze()["outcome"] == "proven"
    search = newclid(problem)
    if search["status"] == "found":
        retained = problem.model_copy(deep=True)
        for relation in retained.conditions:
            relation.enabled = relation.id in search["assumptionIds"]
        assert ConstraintSystem(retained).analyze()["outcome"] == "proven", search

    # Without a nonzero DB, ED=BD also permits E=D=B, a zero-radius object
    # excluded by this application's on_circle relation.
    problem.conditions[1].enabled = False
    result = ConstraintSystem(problem).analyze()
    assert result["outcome"] == "counterexample"
    assert result["counterexample"]["verified"]
