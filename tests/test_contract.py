"""The frozen backend honours its data contract (contracts/data_contract.yaml)."""
import pytest

from celeris.contract import check_dataset, dataset_path, load_contract

NAMES = sorted(load_contract()["datasets"])


@pytest.mark.parametrize("name", NAMES)
def test_dataset_conforms(name):
    if not dataset_path(name).exists():
        pytest.skip(f"{name}: run the pipeline stage '{load_contract()['datasets'][name]['stage']}' first")
    assert check_dataset(name) == []


def test_contract_names_views_for_every_dataset():
    views = {d.get("view") for d in load_contract()["datasets"].values()}
    assert {"forecast", "accuracy", "planning", "anomalies", "data_quality", "executive", "risk", "scenario"} <= views


def test_final_validation_passed():
    p = dataset_path("validation_report")
    if not p.exists():
        pytest.skip("run the final stage first")
    import json
    rep = json.loads(p.read_text(encoding="utf-8"))
    assert rep["status"] == "PASS", rep["checks"]
