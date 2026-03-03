import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest import mock


def _install_bpy_stub():
    bpy_module = types.ModuleType("bpy")
    bpy_types = types.ModuleType("bpy.types")
    bpy_props = types.ModuleType("bpy.props")

    class Operator:
        pass

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

    def _property_stub(**kwargs):
        return kwargs

    bpy_types.Operator = Operator
    bpy_types.Panel = Panel
    bpy_types.AddonPreferences = AddonPreferences
    bpy_types.PropertyGroup = PropertyGroup
    bpy_types.UIList = UIList
    bpy_types.Scene = Scene

    bpy_props.BoolProperty = _property_stub
    bpy_props.StringProperty = _property_stub
    bpy_props.EnumProperty = _property_stub
    bpy_props.IntProperty = _property_stub
    bpy_props.CollectionProperty = _property_stub

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
    )

    sys.modules["bpy"] = bpy_module
    sys.modules["bpy.types"] = bpy_types
    sys.modules["bpy.props"] = bpy_props


def _load_common_module():
    _install_bpy_stub()
    module_name = "suzanne_common_under_test"
    module_path = pathlib.Path(__file__).resolve().parents[1] / "common.py"

    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


common = _load_common_module()


def test_clean_markdown_removes_headers_formatting_and_number_markers():
    raw_text = "# Header\n**Bold** `code`\n2. Step two"

    cleaned = common._clean_markdown(raw_text)

    assert cleaned == "Header\nBold code\n2) Step two"


def test_preview_response_lines_truncates_and_reports_toggle_state():
    text = "\n".join(f"line {index}" for index in range(1, 6))

    preview, needs_toggle = common._preview_response_lines(
        text,
        width=80,
        max_lines=3,
        expanded=False,
    )

    assert preview == ["line 1", "line 2", "line 3"]
    assert needs_toggle is True


def test_preview_response_lines_returns_full_content_when_expanded():
    text = "\n".join(f"line {index}" for index in range(1, 5))

    preview, needs_toggle = common._preview_response_lines(
        text,
        width=80,
        max_lines=2,
        expanded=True,
    )

    assert preview == ["line 1", "line 2", "line 3", "line 4"]
    assert needs_toggle is True


def test_status_visual_maps_recording_error_sent_and_idle_states():
    assert common._status_visual("Anything", True) == ("Anything", "REC", True)
    assert common._status_visual("Idle (error)", False) == ("Idle (error)", "ERROR", True)
    assert common._status_visual("Sending...", False) == ("Sending...", "TIME", False)
    assert common._status_visual("Idle (sent)", False) == ("Idle (sent)", "CHECKMARK", False)
    assert common._status_visual("", False) == ("Idle", "INFO", False)


def test_clip_text_adds_ellipsis_when_limit_is_exceeded():
    clipped = common._clip_text("abcdefghijklmnopqrstuvwxyz", 10)

    assert clipped == "abcdefg..."


def test_conversation_title_from_seed_uses_first_non_empty_line():
    title = common._conversation_title_from_seed(
        "\n\nFirst useful line\nSecond line",
    )

    assert title == "First useful line"


def test_normalize_conversation_keeps_only_valid_messages():
    normalized = common._normalize_conversation(
        {
            "id": "abc12345",
            "created_at": "2026-03-02T10:00:00",
            "updated_at": "2026-03-02T11:00:00",
            "messages": [
                {"role": "user", "text": "Hello", "source": "text", "timestamp": "t1"},
                {"role": "assistant", "text": "Hi there", "source": "assistant", "timestamp": "t2"},
                {"role": "system", "text": "skip me"},
                {"role": "user", "text": "   "},
                "not-a-dict",
            ],
        }
    )

    assert normalized["id"] == "abc12345"
    assert normalized["title"] == "Conversation abc12345"
    assert normalized["messages"] == [
        {
            "role": "user",
            "text": "Hello",
            "source": "text",
            "timestamp": "t1",
        },
        {
            "role": "assistant",
            "text": "Hi there",
            "source": "assistant",
            "timestamp": "t2",
        },
    ]


def test_build_markdown_input_includes_context_sections_in_order():
    built = common._build_markdown_input(
        "How do I bevel an edge?",
        "bpy.ops.mesh.bevel()",
        is_voice=True,
        conversation_context_text="## Previous Conversation Context\n```text\nUser: Hi\n```",
    )

    assert built.startswith("## Assistant Guidance")
    assert "## Previous Conversation Context" in built
    assert "## Voice Transcript\nHow do I bevel an edge?" in built
    assert "## Blender Session History (last 100 lines)" in built


def test_merge_tail_lines_deduplicates_and_keeps_latest_lines():
    merged = common._merge_tail_lines(
        "line 1\nline 2",
        "line 2\nline 3\nline 4",
        limit=3,
    )

    assert merged == "line 2\nline 3\nline 4"


def test_conversation_context_block_uses_recent_turns_only():
    scene = SimpleNamespace(
        suzanne_va_use_conversation_context=True,
        suzanne_va_context_turns=2,
    )
    conversation = {
        "messages": [
            {"role": "user", "text": "Question 1"},
            {"role": "assistant", "text": "Answer 1"},
            {"role": "user", "text": "Question 2"},
            {"role": "assistant", "text": "Answer 2"},
            {"role": "user", "text": "Question 3"},
            {"role": "assistant", "text": "Answer 3"},
        ]
    }

    with mock.patch.object(common, "_get_active_conversation", return_value=(conversation, {})):
        block = common._conversation_context_block(scene)

    assert "Question 1" not in block
    assert "Answer 1" not in block
    assert "User: Question 2" in block
    assert "Assistant: Answer 2" in block
    assert "User: Question 3" in block
    assert "Assistant: Answer 3" in block


def test_conversation_preview_lines_formats_recent_entries():
    scene = SimpleNamespace()
    conversation = {
        "messages": [
            {"role": "user", "text": "Plain text"},
            {"role": "assistant", "text": "# Heading\n**Formatted** reply"},
        ]
    }

    with mock.patch.object(common, "_get_active_conversation", return_value=(conversation, {})):
        lines = common._conversation_preview_lines(scene, max_items=2)

    assert lines == ["You: Plain text", "Suzanne: Heading Formatted reply"]
