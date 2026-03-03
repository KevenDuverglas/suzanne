import importlib
import pathlib
import sys
import types
from contextlib import contextmanager
from types import SimpleNamespace


PACKAGE_NAME = "suzanne"
REPO_PARENT = pathlib.Path(__file__).resolve().parents[2]


def _make_property_stub(kind):
    def _property(**kwargs):
        data = {"kind": kind}
        data.update(kwargs)
        return data

    return _property


def _install_bpy_stub():
    bpy_module = types.ModuleType("bpy")
    bpy_types = types.ModuleType("bpy.types")
    bpy_props = types.ModuleType("bpy.props")

    class Operator:
        def __init__(self):
            self._reports = []

        def report(self, levels, message):
            self._reports.append((set(levels), message))

    class Panel:
        pass

    class AddonPreferences:
        pass

    class PropertyGroup:
        pass

    class UIList:
        pass

    class Scene:
        pass

    @contextmanager
    def _override_context(**_kwargs):
        yield

    bpy_types.Operator = Operator
    bpy_types.Panel = Panel
    bpy_types.AddonPreferences = AddonPreferences
    bpy_types.PropertyGroup = PropertyGroup
    bpy_types.UIList = UIList
    bpy_types.Scene = Scene

    bpy_props.BoolProperty = _make_property_stub("bool")
    bpy_props.StringProperty = _make_property_stub("string")
    bpy_props.EnumProperty = _make_property_stub("enum")
    bpy_props.IntProperty = _make_property_stub("int")
    bpy_props.CollectionProperty = _make_property_stub("collection")

    bpy_module.types = bpy_types
    bpy_module.props = bpy_props
    bpy_module.utils = SimpleNamespace(
        register_class=lambda _cls: None,
        unregister_class=lambda _cls: None,
    )
    bpy_module.ops = SimpleNamespace(
        wm=SimpleNamespace(path_open=lambda **_kwargs: None),
        info=SimpleNamespace(
            select_all=lambda **_kwargs: None,
            report_copy=lambda: None,
        ),
    )
    bpy_module.context = SimpleNamespace(
        window_manager=SimpleNamespace(
            windows=[],
            clipboard="",
            operators=[],
        ),
        preferences=SimpleNamespace(addons={}),
        temp_override=lambda **kwargs: _override_context(**kwargs),
    )

    sys.modules["bpy"] = bpy_module
    sys.modules["bpy.types"] = bpy_types
    sys.modules["bpy.props"] = bpy_props
    return bpy_module


def load_suzanne_modules():
    if str(REPO_PARENT) not in sys.path:
        sys.path.insert(0, str(REPO_PARENT))

    bpy_module = _install_bpy_stub()

    for name in list(sys.modules):
        if name == PACKAGE_NAME or name.startswith(f"{PACKAGE_NAME}."):
            del sys.modules[name]

    importlib.invalidate_caches()

    package = importlib.import_module(PACKAGE_NAME)
    return SimpleNamespace(
        bpy=bpy_module,
        package=package,
        common=importlib.import_module(f"{PACKAGE_NAME}.common"),
        state=importlib.import_module(f"{PACKAGE_NAME}.state"),
        operators=importlib.import_module(f"{PACKAGE_NAME}.operators"),
        panel=importlib.import_module(f"{PACKAGE_NAME}.panel"),
        preferences=importlib.import_module(f"{PACKAGE_NAME}.preferences"),
    )


class FakeCollection:
    def __init__(self, items=None):
        self._items = list(items or [])

    def add(self):
        item = SimpleNamespace(label="", is_placeholder=False)
        self._items.append(item)
        return item

    def remove(self, index):
        del self._items[index]

    def __len__(self):
        return len(self._items)

    def __getitem__(self, index):
        return self._items[index]


class LayoutRecorder:
    def __init__(self, collapsed_props=None):
        self.calls = []
        self.children = []
        self.collapsed_props = set(collapsed_props or [])
        self.enabled = True
        self.alert = False
        self.scale_y = 1.0
        self.alignment = None

    def _child(self):
        child = LayoutRecorder(self.collapsed_props)
        self.children.append(child)
        return child

    def label(self, **kwargs):
        self.calls.append(("label", kwargs))

    def prop(self, *args, **kwargs):
        self.calls.append(("prop", args, kwargs))

    def operator(self, operator_id, **kwargs):
        self.calls.append(("operator", operator_id, kwargs))
        return SimpleNamespace()

    def separator(self):
        self.calls.append(("separator",))

    def row(self, align=False):
        row = self._child()
        self.calls.append(("row", align, row))
        return row

    def column(self, align=False):
        column = self._child()
        self.calls.append(("column", align, column))
        return column

    def box(self):
        box = self._child()
        self.calls.append(("box", box))
        return box

    def panel_prop(self, _scene, prop_name):
        header = self._child()
        body = None if prop_name in self.collapsed_props else self._child()
        self.calls.append(("panel_prop", prop_name, header, body))
        return header, body

    def template_list(self, *args, **kwargs):
        self.calls.append(("template_list", args, kwargs))

    def _all_recorders(self):
        yield self
        for child in self.children:
            yield from child._all_recorders()

    def label_texts(self):
        texts = []
        for recorder in self._all_recorders():
            for call in recorder.calls:
                if call[0] == "label":
                    texts.append(call[1].get("text", ""))
        return texts

    def operator_ids(self):
        operator_ids = []
        for recorder in self._all_recorders():
            for call in recorder.calls:
                if call[0] == "operator":
                    operator_ids.append(call[1])
        return operator_ids


def make_preferences(**overrides):
    values = {
        "api_key": "sk-test",
        "show_api_key": False,
        "response_model": "gpt-4o-mini",
        "transcription_model": "gpt-4o-mini-transcribe",
        "audio_input_device": "system_default",
        "file_prefix": "suzanne_va_",
        "auto_save_conversations": True,
        "diagnostics_last_message": "",
        "diagnostics_last_error": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_scene(**overrides):
    values = {
        "suzanne_va_prompt": "",
        "suzanne_va_include_info_history": False,
        "suzanne_va_last_info_history": "",
        "suzanne_va_status": "Idle",
        "suzanne_va_last_transcript": "",
        "suzanne_va_last_response": "",
        "suzanne_va_expand_transcript": False,
        "suzanne_va_expand_response": False,
        "suzanne_va_mic_active": False,
        "suzanne_va_context_turns": 4,
        "suzanne_va_active_conversation": "",
        "suzanne_va_conversation_preview": FakeCollection(),
        "suzanne_va_conversation_preview_index": 0,
        "suzanne_va_output_view": "response",
        "suzanne_va_show_message": True,
        "suzanne_va_show_context": True,
        "suzanne_va_show_conversation": True,
        "suzanne_va_show_recording": True,
        "suzanne_va_show_output": True,
        "suzanne_va_use_conversation_context": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_context(addon_module_name, scene=None, prefs=None):
    scene = scene or make_scene()
    prefs = prefs or make_preferences()
    window_manager = SimpleNamespace(
        clipboard="",
        invoke_props_dialog=lambda _operator: "DIALOG",
        invoke_confirm=lambda _operator, _event: "CONFIRM",
    )
    return SimpleNamespace(
        scene=scene,
        area=SimpleNamespace(type="VIEW_3D"),
        window_manager=window_manager,
        preferences=SimpleNamespace(
            addons={addon_module_name: SimpleNamespace(preferences=prefs)}
        ),
    )


def test_load_suzanne_modules_inserts_repo_parent_when_missing():
    original_path = list(sys.path)
    trimmed_path = [entry for entry in original_path if entry != str(REPO_PARENT)]

    importlib.invalidate_caches()

    try:
        sys.path[:] = trimmed_path
        modules = load_suzanne_modules()
        assert sys.path[0] == str(REPO_PARENT)
        assert modules.package.__name__ == PACKAGE_NAME
    finally:
        sys.path[:] = original_path
