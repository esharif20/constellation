import json
from pathlib import Path

from constellation.verdict_types import Assessment, Evidence, ItemEvidence, Reason

FIX = Path(__file__).parent / "fixtures" / "assess"


def test_fixture_loads_into_contract_types() -> None:
    setup = json.loads((FIX / "setup.json").read_text())
    ev = setup["evidence"]
    evidence = Evidence(
        **{
            **ev,
            "projects": {k: tuple(v) for k, v in ev["projects"].items()},
            "items": {k: ItemEvidence(**v) for k, v in ev["items"].items()},
        }
    )
    assert evidence.active_days == 34
    expected = [
        Assessment(**{**a, "reasons": tuple(Reason(**r) for r in a["reasons"])})
        for a in json.loads((FIX / "expected.json").read_text())["assessments"]
    ]
    assert len(expected) == len(setup["items"]) == 12
