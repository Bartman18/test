"""
Unit-test conftest.py — applies to all tests under tests/unit/

Fixes the Lambda handler module-cache collision.

Problem
-------
All three Lambda functions live in separate directories but share the same
filename: handler.py.  Python's module cache (sys.modules) stores modules by
their *import name*, not by file path.  When pytest collects all three test
files in a single session it adds all three lambda directories to sys.path.
The first test to run imports 'handler' and Python caches it; every subsequent
test file that does `from handler import lambda_handler` gets that same
(wrong) cached module.

Solution
--------
The `isolate_lambda_handler` autouse fixture runs before every test function:
  1. Removes all lambda directories from sys.path.
  2. Inserts only the lambda directory that belongs to the current test file.
  3. Evicts 'handler' from sys.modules so @patch and `from handler import …`
     both resolve a fresh import from the correct directory.
After the test it evicts 'handler' again to leave a clean state.

Order of operations (pytest internals)
---------------------------------------
  1. autouse fixture runs  ← sys.path fixed + handler evicted
  2. @patch("handler.X") enters  ← imports fresh handler from correct dir
  3. test body runs  ← `from handler import lambda_handler` hits cached entry
  4. @patch exits  ← restores original attribute
  5. autouse fixture teardown  ← evicts handler again
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Map test filename → absolute path of its Lambda directory
_HANDLER_DIRS: dict[str, str] = {
    "test_post_feedback.py": os.path.join(_PROJECT_ROOT, "lambda", "post_feedback"),
    "test_get_recommendation.py": os.path.join(_PROJECT_ROOT, "lambda", "get_recommendation"),
    "test_process_feedback.py": os.path.join(_PROJECT_ROOT, "lambda", "process_feedback"),
}

_ALL_LAMBDA_DIRS: set[str] = set(_HANDLER_DIRS.values())


@pytest.fixture(autouse=True)
def isolate_lambda_handler(request: pytest.FixtureRequest):
    """Isolate the 'handler' module so each test file imports its own Lambda."""
    test_file = os.path.basename(str(request.fspath))
    target_dir = _HANDLER_DIRS.get(test_file)

    if target_dir:
        # 1. Remove ALL lambda dirs then insert only the correct one at [0]
        sys.path[:] = [p for p in sys.path if p not in _ALL_LAMBDA_DIRS]
        sys.path.insert(0, target_dir)

        # 2. Force a fresh import for this test
        sys.modules.pop("handler", None)

    yield

    # Teardown: evict to avoid leaking into the next test
    sys.modules.pop("handler", None)
