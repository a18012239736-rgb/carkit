from concurrent.futures import ThreadPoolExecutor
from api.bridge import Bridge


def test_bridge_uses_single_browser_executor(tmp_path):
    bridge = Bridge(str(tmp_path))
    assert bridge._acquire_executor._max_workers == 1
    # The executor is intentionally shared by every browser operation.
    assert isinstance(bridge._acquire_executor, ThreadPoolExecutor)
    bridge._acquire_executor.shutdown(wait=True)
