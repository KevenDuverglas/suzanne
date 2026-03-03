import importlib
import pathlib
import runpy
import sys
from unittest import mock

import pytest

from tests.test_support import load_suzanne_modules


PACKAGE_NAME = "suzanne"
REPO_PARENT = pathlib.Path(__file__).resolve().parents[2]


def _load_package_without_bpy():
    if str(REPO_PARENT) not in sys.path:
        sys.path.insert(0, str(REPO_PARENT))

    for name in list(sys.modules):
        if name == "bpy" or name.startswith("bpy."):
            del sys.modules[name]
        if name == PACKAGE_NAME or name.startswith(f"{PACKAGE_NAME}."):
            del sys.modules[name]

    importlib.invalidate_caches()
    return importlib.import_module(PACKAGE_NAME)


def test_addon_register_registers_classes_and_runs_setup_hooks():
    modules = load_suzanne_modules()
    classes = (object(), object(), object())
    events = []

    with mock.patch.object(modules.package, "classes", classes):
        with mock.patch.object(
            modules.package.bpy.utils,
            "register_class",
            side_effect=lambda cls: events.append(("register", cls)),
        ):
            with mock.patch.object(
                modules.package,
                "ensure_props",
                side_effect=lambda: events.append(("ensure_props", None)),
            ):
                with mock.patch.object(
                    modules.package,
                    "_ensure_recordings_dir",
                    side_effect=lambda: events.append(("ensure_recordings_dir", None)),
                ):
                    modules.package.register()

    assert events == [
        ("register", classes[0]),
        ("register", classes[1]),
        ("register", classes[2]),
        ("ensure_props", None),
        ("ensure_recordings_dir", None),
    ]


def test_addon_unregister_clears_props_then_unregisters_in_reverse_order():
    modules = load_suzanne_modules()
    classes = (object(), object(), object())
    events = []

    with mock.patch.object(modules.package, "classes", classes):
        with mock.patch.object(
            modules.package,
            "clear_props",
            side_effect=lambda: events.append(("clear_props", None)),
        ):
            with mock.patch.object(
                modules.package.bpy.utils,
                "unregister_class",
                side_effect=lambda cls: events.append(("unregister", cls)),
            ):
                modules.package.unregister()

    assert events == [
        ("clear_props", None),
        ("unregister", classes[2]),
        ("unregister", classes[1]),
        ("unregister", classes[0]),
    ]


def test_addon_register_requires_blender_and_unregister_noops_without_bpy():
    package = _load_package_without_bpy()

    with pytest.raises(RuntimeError, match="must be registered from Blender"):
        package.register()

    assert package.unregister() is None


def test_addon_main_entry_calls_register_when_run_as_script():
    init_path = pathlib.Path(__file__).resolve().parents[1] / "__init__.py"

    for name in list(sys.modules):
        if name == "bpy" or name.startswith("bpy."):
            del sys.modules[name]
        if name == PACKAGE_NAME or name.startswith(f"{PACKAGE_NAME}."):
            del sys.modules[name]

    with pytest.raises(RuntimeError, match="must be registered from Blender"):
        runpy.run_path(str(init_path), run_name="__main__")
