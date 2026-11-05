from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from agent.bench import Bench


def _bench() -> Bench:
    bench = object.__new__(Bench)
    bench.prepare_app_patch = MagicMock(return_value="/patch")
    bench.git_apply = MagicMock()
    bench.rebuild = MagicMock()
    bench.sync_app_assets = MagicMock()
    bench.restart = MagicMock()
    return bench


class TestPatchApp(unittest.TestCase):
    def test_build_assets_rebuilds_only_the_patched_app_then_syncs_its_assets(self):
        bench = _bench()
        calls = MagicMock()
        calls.attach_mock(bench.rebuild, "rebuild")
        calls.attach_mock(bench.sync_app_assets, "sync_app_assets")
        calls.attach_mock(bench.restart, "restart")

        Bench.patch_app.__wrapped__(bench, "qorshe", "diff", "a.patch", build_assets=True, revert=False)

        self.assertEqual(
            [c[0] for c in calls.mock_calls],
            ["rebuild", "sync_app_assets", "restart"],
        )
        bench.rebuild.assert_called_once_with(["qorshe"])
        bench.sync_app_assets.assert_called_once_with("qorshe")

    def test_patch_without_build_assets_neither_rebuilds_nor_syncs(self):
        bench = _bench()
        Bench.patch_app.__wrapped__(bench, "qorshe", "diff", "a.patch", build_assets=False, revert=False)
        bench.rebuild.assert_not_called()
        bench.sync_app_assets.assert_not_called()
        bench.restart.assert_called_once()

    def test_sync_app_assets_copies_the_app_public_folder_into_sites_assets(self):
        bench = object.__new__(Bench)
        bench.docker_execute = MagicMock()
        Bench.sync_app_assets.__wrapped__(bench, "qorshe")
        bench.docker_execute.assert_called_once_with("cp -a apps/qorshe/qorshe/public/. sites/assets/qorshe/")


if __name__ == "__main__":
    unittest.main()
