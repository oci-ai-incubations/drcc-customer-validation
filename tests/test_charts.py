from drcc_validation.reports.charts import doughnut_data_uri, bar_data_uri


def test_doughnut_returns_png_data_uri():
    uri = doughnut_data_uri(passed=10, errors=2, warnings=1, incomplete=5)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > 200


def test_bar_returns_png_data_uri():
    uri = bar_data_uri(
        labels=["compute", "database"],
        errors=[3, 1],
        warnings=[0, 2],
    )
    assert uri.startswith("data:image/png;base64,")
