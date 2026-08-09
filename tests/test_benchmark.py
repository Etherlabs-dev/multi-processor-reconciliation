from reconciliation.benchmark import run_benchmark


def test_synthetic_benchmark_has_no_false_matches() -> None:
    report = run_benchmark()
    assert report["evidence_label"] == "synthetic"
    assert report["expected_matches"] == 6
    assert report["correct_matches"] == 6
    assert report["false_matches"] == 0
    assert report["unresolved_records"] == 7
    assert report["duplicate_records"] == 1
