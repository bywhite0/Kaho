import os
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


REALDATA_MODULES = [
    "tests.test_data_manager_index",
    "tests.test_skill_structured",
    "tests.test_plugins_commands",
    "tests.test_data_store",
    "tests.test_formatters",
]


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        os.environ["KAHO_REAL_MASTERDATA_DIR"] = sys.argv[1].strip()
    os.environ["KAHO_ENABLE_REALDATA_TESTS"] = "1"

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(REALDATA_MODULES)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
