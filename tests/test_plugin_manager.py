"""Test plugin manager — Tier 3 auto-install/uninstall."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))


def test_get_project_plugins_with_plugins_field():
    from plugin_manager import get_project_plugins

    project = {"project_md": "# test\nPlugins: playwright, greptile\nStatus: active"}
    assert get_project_plugins(project) == {"playwright", "greptile"}


def test_get_project_plugins_without_field():
    from plugin_manager import get_project_plugins

    project = {"project_md": "# test\nStatus: active"}
    assert get_project_plugins(project) == set()


def test_get_project_plugins_empty_md():
    from plugin_manager import get_project_plugins

    assert get_project_plugins({}) == set()
    assert get_project_plugins({"project_md": ""}) == set()


def test_get_project_plugins_single():
    from plugin_manager import get_project_plugins

    project = {"project_md": "Plugins: playwright"}
    assert get_project_plugins(project) == {"playwright"}


def test_permanent_plugins_not_in_tier3():
    from plugin_manager import PERMANENT_PLUGINS, TIER3_PLUGINS

    overlap = PERMANENT_PLUGINS & set(TIER3_PLUGINS.keys())
    assert overlap == set(), f"Overlap between permanent and tier3: {overlap}"
