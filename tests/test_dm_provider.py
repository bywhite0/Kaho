import unittest
from unittest.mock import AsyncMock, patch


class DMProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_init_dm_singleton(self):
        import src.core.services.dm_provider as dm_provider

        old_dm = dm_provider._dm
        try:
            dm_provider._dm = None

            class _FakeDM:
                def __init__(self, data_dir):
                    self.data_dir = data_dir

                def sync_version_cache(self, _version_path):
                    return True

            fake_to_thread = AsyncMock(return_value=True)
            with patch.object(dm_provider, "DataManager", _FakeDM), patch.object(
                dm_provider.asyncio, "to_thread", fake_to_thread
            ):
                dm1 = await dm_provider.init_dm()
                dm2 = await dm_provider.init_dm()

            self.assertIs(dm1, dm2)
            self.assertIs(dm_provider.get_dm(), dm1)
            fake_to_thread.assert_awaited_once()
        finally:
            dm_provider._dm = old_dm

    def test_get_paths(self):
        import src.core.services.dm_provider as dm_provider

        root_dir, data_dir, version_path = dm_provider.get_paths()
        self.assertTrue(root_dir)
        self.assertTrue(data_dir.endswith("masterdata"))
        self.assertTrue(version_path.endswith("currentVersion.txt"))


if __name__ == "__main__":
    unittest.main()

