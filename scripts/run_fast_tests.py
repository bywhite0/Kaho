import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


FAST_MODULES = [
    "tests.test_runtime_refresh",
    "tests.test_t2i_service",
    "tests.test_dm_provider",
]


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(FAST_MODULES)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
