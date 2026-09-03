"""运行 gallery 插件的全部单元测试：python run_tests.py

不经 pytest 收集：插件包目录带 __init__.py，pytest 会为构造模块名而导入
src.plugins.gallery，进而触发未初始化的 NoneBot 依赖，整批测试直接 collect 失败。
这里自行加载模块、调用 test_* 函数，并为需要 tmp_path 的用例准备临时目录。
"""

import importlib
import inspect
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

TEST_MODULES = (
    "test_access_core",
    "test_names",
    "test_image_hash",
)

SUBPROCESS_SCRIPTS = (
    "test_gallery_state.py",
    "smoke_load_plugin.py",
)
"""这些脚本要初始化 NoneBot 并设置进程级的 LOCALSTORE_* 环境变量，
必须各自独占一个进程，否则会与合成包加载的模块互相污染。"""


def _run_case(func) -> None:
    if "tmp_path" in inspect.signature(func).parameters:
        with tempfile.TemporaryDirectory(prefix="gallery_test_") as tmp_dir:
            func(Path(tmp_dir))
    else:
        func()


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    passed = 0
    failed: list[str] = []
    for module_name in TEST_MODULES:
        module = importlib.import_module(module_name)
        for case_name in sorted(vars(module)):
            if not case_name.startswith("test_"):
                continue
            func = getattr(module, case_name)
            if not callable(func):
                continue
            try:
                _run_case(func)
            except Exception:
                failed.append(f"{module_name}.{case_name}")
                print(f"FAIL {module_name}.{case_name}")
                traceback.print_exc()
            else:
                passed += 1

    print(f"\n进程内用例：{passed} passed, {len(failed)} failed")
    for case in failed:
        print(f"  failed: {case}")

    tests_dir = Path(__file__).resolve().parent
    for script in SUBPROCESS_SCRIPTS:
        print(f"\n--- {script} ---")
        result = subprocess.run(
            [sys.executable, script],
            cwd=tests_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        summary = [line for line in (result.stdout or "").splitlines() if line.strip()]
        print("\n".join(summary[-3:]))
        if result.returncode != 0:
            failed.append(script)
            print(result.stderr or "", file=sys.stderr)

    print(f"\n{'FAILED: ' + ', '.join(failed) if failed else 'ALL PASSED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
