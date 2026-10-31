import pytest

# Other tests import this support module before declaring it as a local plugin.
# Register rewriting before that first import; do not widen its fixture scope.
pytest.register_assert_rewrite("backend.tests.forecast_quality.authority_loader_fixture")

pytest_plugins = ["backend.tests.harvest_state.conftest"]
