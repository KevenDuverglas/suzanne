import json
import os
import pathlib
import tempfile
from types import SimpleNamespace
from unittest import mock

from tests.test_support import LayoutRecorder, load_suzanne_modules, make_context, make_preferences


def test_common_text_and_ui_helpers_cover_basic_rendering_paths():
    modules = load_suzanne_modules()
    common = modules.common

    redrawn = []
    area_one = SimpleNamespace(tag_redraw=lambda: redrawn.append("one"))
    area_two = SimpleNamespace(tag_redraw=lambda: redrawn.append("two"))
    common.bpy.context.window_manager.windows = [
        SimpleNamespace(screen=None),
        SimpleNamespace(screen=SimpleNamespace(areas=[area_one, area_two])),
    ]

    common._tag_redraw_all()

    assert redrawn == ["one", "two"]
    assert common._wrap_ui_text("", width=4) == [""]
    assert common._wrap_ui_text("abcde\n\nxyz", width=4) == ["abcd", "e", "", "xyz"]
    assert common._response_lines("# Header\n**Bold**", width=20) == ["Header", "Bold"]

    header_box = LayoutRecorder()
    scene = SimpleNamespace(section_open=False, expanded=True)
    assert common._draw_section_header(header_box, scene, "section_open", "Title", "INFO") is False
    row = header_box.children[0]
    prop_call = next(call for call in row.calls if call[0] == "prop")
    assert prop_call[2]["icon"] == "TRIA_RIGHT"

    toggle_layout = LayoutRecorder()
    common._draw_expand_toggle(toggle_layout, scene, "expanded")
    assert toggle_layout.calls[0][2]["text"] == "Show less"

    assert "Answer only about Blender" in common._blender_only_prefix("Hello")
    assert common._tail_lines("a\nb\nc", 2) == "b\nc"
    assert common._tail_lines("a", 0) == ""
    assert "Assistant Guidance" in common._history_guidance_block()


def test_common_ffmpeg_and_enum_helpers_cover_resolution_paths():
    modules = load_suzanne_modules()
    common = modules.common

    cache = []
    assert common._set_enum_items_cache(cache, [(1, 2, 3)]) == [("1", "2", "3")]

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = pathlib.Path(tmpdir)
        override_path = addon_dir / "override_ffmpeg.exe"
        override_path.write_text("", encoding="utf-8")
        bundled_path = addon_dir / "bin" / "ffmpeg.exe"
        bundled_path.parent.mkdir(parents=True, exist_ok=True)
        bundled_path.write_text("", encoding="utf-8")

        with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
            with mock.patch.object(common.platform, "system", return_value="Windows"):
                windows_candidates = common._bundled_ffmpeg_candidates()
            with mock.patch.object(common.platform, "system", return_value="Darwin"):
                mac_candidates = common._bundled_ffmpeg_candidates()
            with mock.patch.object(common.platform, "system", return_value="Linux"):
                linux_candidates = common._bundled_ffmpeg_candidates()

        assert windows_candidates[0].parts[-3:] == ("bin", "windows", "ffmpeg.exe")
        assert mac_candidates[0].parts[-3:] == ("bin", "macos", "ffmpeg")
        assert linux_candidates[0].parts[-3:] == ("bin", "linux", "ffmpeg")

        with mock.patch.dict(common.os.environ, {common._FFMPEG_ENV_VAR: f'"{override_path}"'}, clear=False):
            assert common._resolve_ffmpeg_path() == str(override_path)

        with mock.patch.dict(common.os.environ, {common._FFMPEG_ENV_VAR: ""}, clear=False):
            with mock.patch.object(common, "_bundled_ffmpeg_candidates", return_value=[bundled_path]):
                with mock.patch.object(common.shutil, "which", return_value="ffmpeg-on-path"):
                    assert common._resolve_ffmpeg_path() == str(bundled_path)

        with mock.patch.dict(common.os.environ, {common._FFMPEG_ENV_VAR: ""}, clear=False):
            with mock.patch.object(common, "_bundled_ffmpeg_candidates", return_value=[]):
                with mock.patch.object(common.shutil, "which", return_value="ffmpeg-on-path"):
                    assert common._resolve_ffmpeg_path() == "ffmpeg-on-path"


def test_common_info_history_helpers_cover_lookup_copy_and_snapshot_paths():
    modules = load_suzanne_modules()
    common = modules.common

    space = SimpleNamespace(
        show_report_debug=False,
        show_report_info=False,
        show_report_operator=False,
        show_report_warning=False,
        show_report_error=False,
    )
    window_region = SimpleNamespace(type="WINDOW")
    info_area = SimpleNamespace(
        type="INFO",
        regions=[SimpleNamespace(type="UI"), window_region],
        spaces=SimpleNamespace(active=space),
    )
    common.bpy.context.window_manager.windows = [
        SimpleNamespace(screen=SimpleNamespace(areas=[info_area]))
    ]

    override = common._find_area_context("INFO")
    assert override["region"] is window_region

    common._enable_info_filters(info_area)
    assert space.show_report_debug is True
    assert space.show_report_info is True
    assert space.show_report_operator is True
    assert space.show_report_warning is True
    assert space.show_report_error is True

    with mock.patch.object(common.bpy.ops.info, "select_all") as select_all:
        with mock.patch.object(
            common.bpy.ops.info,
            "report_copy",
            side_effect=lambda: setattr(common.bpy.context.window_manager, "clipboard", "copied"),
        ):
            common.bpy.context.window_manager.clipboard = ""
            assert common._copy_info_reports_with_override(override) == "copied"
            select_all.assert_called_once_with(action="SELECT")

    temp_area = SimpleNamespace(
        type="VIEW_3D",
        regions=[SimpleNamespace(type="WINDOW")],
    )
    common.bpy.context.window_manager.windows = [
        SimpleNamespace(screen=SimpleNamespace(areas=[temp_area]))
    ]
    with mock.patch.object(
        common,
        "_copy_info_reports_with_override",
        side_effect=lambda ctx: "temp history" if ctx["area"].type == "INFO" else "",
    ):
        assert common._copy_info_reports_with_temp_area() == "temp history"
    assert temp_area.type == "VIEW_3D"

    prop_default = SimpleNamespace(identifier="rna_type", is_readonly=False, default=None)
    prop_value = SimpleNamespace(identifier="value", is_readonly=False, default="default")
    operator = SimpleNamespace(
        bl_idname="mesh.test",
        bl_rna=SimpleNamespace(properties=[prop_default, prop_value]),
        value="custom",
    )
    common.bpy.context.window_manager.operators = [operator]
    assert common._operator_snapshot_lines(5) == "mesh.test(value='custom')"

    common.bpy.context.window_manager.clipboard = "keep"
    with mock.patch.object(common, "_find_area_context", return_value=None):
        with mock.patch.object(common, "_copy_info_reports_with_temp_area", return_value="Report line"):
            with mock.patch.object(common, "_operator_snapshot_lines", return_value="Operator line"):
                assert common._get_info_history_lines(limit=3) == "Report line\nOperator line"
    assert common.bpy.context.window_manager.clipboard == "keep"


def test_common_model_preferences_and_audio_helpers_cover_parsing_and_defaults():
    modules = load_suzanne_modules()
    common = modules.common

    assert common._get_models_from_api("") == []
    with mock.patch.object(
        common,
        "_get_json",
        return_value=json.dumps({"data": [{"id": "z"}, {"id": "a"}, {"id": "z"}, {}]}),
    ):
        assert common._get_models_from_api("sk-live") == ["a", "z"]

    with mock.patch.object(common, "_get_models_from_api", return_value=["fresh-model"]):
        with mock.patch.object(common.time, "time", return_value=123.0):
            common._MODELS_CACHE["ids"] = []
            common._MODELS_CACHE["ts"] = 0.0
            assert common._get_models_cached("sk-live", force=True) == ["fresh-model"]
            assert common._MODELS_CACHE["ts"] == 123.0

    prefs = make_preferences(api_key="  sk-live  ")
    context = make_context(common.ADDON_MODULE, prefs=prefs)
    assert common._get_addon_preferences(context) is prefs
    assert common._get_effective_api_key(prefs) == "sk-live"

    common._set_diagnostics_message(prefs, message="m" * 300, error="e" * 300)
    assert prefs.diagnostics_last_message.endswith("...")
    assert prefs.diagnostics_last_error.endswith("...")

    with mock.patch.object(common, "_get_addon_preferences", return_value=prefs):
        with mock.patch.object(common, "_get_models_cached", return_value=[]):
            assert common._model_enum_items(None, context) == [("gpt-4o-mini", "gpt-4o-mini", "")]

        with mock.patch.object(
            common,
            "_get_models_cached",
            return_value=["base-model", "whisper-1", "custom-transcribe"],
        ):
            assert common._transcribe_model_enum_items(None, context) == [
                ("whisper-1", "whisper-1", ""),
                ("custom-transcribe", "custom-transcribe", ""),
            ]

    with mock.patch.object(common.shutil, "which", return_value=None):
        assert common._get_audio_devices_linux() == [("default", "default", "default")]

    fake_linux_proc = SimpleNamespace(communicate=lambda timeout: (b"default\npulse\nhw:1\n", b""))
    with mock.patch.object(common.shutil, "which", return_value="arecord"):
        with mock.patch.object(common.subprocess, "Popen", return_value=fake_linux_proc):
            assert common._get_audio_devices_linux() == [
                ("default", "default", "default"),
                ("hw:1", "hw:1", "hw:1"),
            ]

    with mock.patch.object(common, "_resolve_ffmpeg_path", return_value=None):
        assert common._get_audio_devices_windows() == [("default", "default", "default")]

    fake_windows_proc = SimpleNamespace(
        communicate=lambda timeout: (
            b"",
            b'DirectShow audio devices\n  "Mic One"\n  "Mic Two" (audio)\n',
        )
    )
    with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
        with mock.patch.object(common.subprocess, "Popen", return_value=fake_windows_proc):
            windows_items = common._get_audio_devices_windows()
    assert ("Mic One", "Mic One", "Mic One") in windows_items
    assert ("Mic Two", "Mic Two", "Mic Two") in windows_items

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = pathlib.Path(tmpdir)
        atunc_path = addon_dir / "atunc" / "atunc"
        atunc_path.parent.mkdir(parents=True, exist_ok=True)
        atunc_path.write_text("", encoding="utf-8")
        fake_macos_proc = SimpleNamespace(
            communicate=lambda timeout: (b'[{"id": 7, "name": "Built-in Mic"}]', b"")
        )
        with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
            with mock.patch.object(common.subprocess, "Popen", return_value=fake_macos_proc):
                assert common._get_audio_devices_macos() == [("7", "Built-in Mic", "Built-in Mic")]

    assert common._first_non_default_audio_device(
        [("default", "default", "default"), (" Mic ", "Mic", "Mic")]
    ) == "Mic"

    with mock.patch.object(common.platform, "system", return_value="Darwin"):
        assert common._os_display_name() == "macOS"
    with mock.patch.object(common.platform, "system", return_value=""):
        assert common._os_display_name() == "Unknown"


def test_common_probe_storage_and_conversation_helpers_cover_disk_workflows():
    modules = load_suzanne_modules()
    common = modules.common

    with mock.patch.object(common.bpy.ops.wm, "path_open", return_value=None):
        assert common._show_file_in_os("C:/temp") is True
    with mock.patch.object(common.bpy.ops.wm, "path_open", side_effect=RuntimeError("boom")):
        assert common._show_file_in_os("C:/temp") is False

    with mock.patch.object(common.platform, "system", return_value="Windows"):
        with mock.patch.object(
            common,
            "_get_audio_devices_windows",
            return_value=[("default", "default", "default"), ("USB Mic", "USB Mic", "USB Mic")],
        ):
            probe_candidates = common._microphone_probe_candidates("ffmpeg", "probe.wav")
    assert any("audio=USB Mic" in part for args in probe_candidates for part in args)

    with mock.patch.object(common.platform, "system", return_value="Linux"):
        with mock.patch.object(common, "_resolve_ffmpeg_path", return_value=None):
            success, detail = common._run_microphone_probe()
    assert success is False
    assert "ffmpeg is unavailable" in detail

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        silence_path = handle.name
    try:
        common._write_silence_wav(silence_path, duration_s=0.01)
        assert common.os.path.getsize(silence_path) > 44
    finally:
        if os.path.exists(silence_path):
            os.remove(silence_path)

    with mock.patch.object(common, "_os_display_name", return_value="Linux"):
        with mock.patch.object(common.time, "time", return_value=456.0):
            common._AUDIO_DEVICES_CACHE["items"] = []
            device_items = common._audio_devices_enum_items(None, None)
    assert device_items[0][0] == common._SYSTEM_AUDIO_DEVICE_ID
    assert common._AUDIO_DEVICES_CACHE["ts"] == 456.0

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = pathlib.Path(tmpdir)
        scene = SimpleNamespace(
            suzanne_va_active_conversation="",
            suzanne_va_use_conversation_context=True,
            suzanne_va_context_turns=1,
        )

        with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
            data_dir = common._conversation_storage_dir()
            assert data_dir == addon_dir / "data"
            assert common._conversation_store_path() == data_dir / common._CONVERSATION_FILE_NAME
            assert common._load_conversation_store() == common._empty_conversation_store()

            created = common._new_conversation(scene, title_seed="First line\nSecond line")
            assert created is not None

            loaded_store = common._load_conversation_store()
            assert len(loaded_store["conversations"]) == 1
            assert common._sorted_conversations(loaded_store)[0]["id"] == created["id"]
            assert common._find_conversation(loaded_store, created["id"])["id"] == created["id"]

            enum_items = common._conversation_enum_items(None, None)
            assert enum_items[0][0] == common._NO_CONVERSATION_ID
            assert enum_items[1][0] == created["id"]

            assert common._append_conversation_exchange(scene, "User asks", "Assistant answers", "text") is True
            loaded_store = common._load_conversation_store()
            conversation = common._find_conversation(loaded_store, created["id"])
            assert len(conversation["messages"]) == 2

            context_block = common._conversation_context_block(scene)
            assert "User: User asks" in context_block
            assert "Assistant: Assistant answers" in context_block
            assert common._conversation_preview_lines(scene, max_items=2) == [
                "You: User asks",
                "Suzanne: Assistant answers",
            ]

            assert common._rename_conversation(scene, "Renamed conversation") is True

            scene.suzanne_va_active_conversation = ""
            selected_id = common._sync_active_conversation(scene, common._load_conversation_store())
            assert selected_id

            active_conversation, _ = common._get_active_conversation(scene, create_if_missing=False)
            assert active_conversation["id"] == selected_id

            with mock.patch.object(
                common,
                "_get_addon_preferences",
                return_value=SimpleNamespace(auto_save_conversations=False),
            ):
                assert common._append_conversation_exchange(scene, "Skip", "Skip", "text") is True

            assert common._delete_active_conversation(scene) is True
            assert common._load_conversation_store()["conversations"] == []


def test_common_http_helpers_cover_request_wrappers_and_api_shims():
    modules = load_suzanne_modules()
    common = modules.common

    assert common._build_openai_headers("  sk-live ") == {
        "Authorization": "Bearer sk-live",
        "User-Agent": "Suzanne-VA-Addon/1.7.0",
    }

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self.payload

    responses = iter(['{"posted": true}', '{"data": []}', '{"multipart": true}'])
    captured = []

    def fake_urlopen(req, timeout):
        captured.append((req, timeout))
        return FakeResponse(next(responses))

    with mock.patch.object(common, "urlopen", side_effect=fake_urlopen):
        assert common._post_json("https://example.com/json", "sk-live", {"hello": "world"}) == '{"posted": true}'
        assert common._get_json("https://example.com/get", "sk-live") == '{"data": []}'
        assert common._post_multipart(
            "https://example.com/upload",
            "sk-live",
            {"field": "value"},
            {"file": ("sample.txt", "text/plain", b"abc")},
        ) == '{"multipart": true}'

    post_headers = {key.lower(): value for key, value in captured[0][0].header_items()}
    multipart_headers = {key.lower(): value for key, value in captured[2][0].header_items()}
    assert captured[0][0].get_method() == "POST"
    assert captured[1][0].get_method() == "GET"
    assert post_headers["content-type"] == "application/json"
    assert multipart_headers["content-type"].startswith("multipart/form-data; boundary=")

    class FakeHttpError:
        def __init__(self, payload=None, should_fail=False):
            self.payload = payload
            self.should_fail = should_fail

        def read(self):
            if self.should_fail:
                raise ValueError("boom")
            return self.payload

    assert common._read_http_error_body(FakeHttpError(b"bad body")) == "bad body"
    assert common._read_http_error_body(FakeHttpError(should_fail=True)) == ""

    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(b"audio-bytes")
        data_path = handle.name
    try:
        assert common._read_file_bytes(data_path) == b"audio-bytes"
    finally:
        if os.path.exists(data_path):
            os.remove(data_path)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(b"RIFFdata")
        audio_path = handle.name
    try:
        with mock.patch.object(common, "_post_multipart", return_value='{"text": "hello"}') as post_multipart:
            assert common._transcribe_audio("sk-live", "whisper-1", audio_path)["text"] == "hello"
            assert post_multipart.call_args[0][0] == "https://api.openai.com/v1/audio/transcriptions"

        with mock.patch.object(common, "_post_json", return_value='{"output_text": "ok"}') as post_json:
            assert common._call_chatgpt("sk-live", "gpt-4o-mini", "Prompt")["output_text"] == "ok"
            post_json.assert_called_once_with(
                "https://api.openai.com/v1/responses",
                "sk-live",
                {"model": "gpt-4o-mini", "input": "Prompt"},
            )
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def test_common_guard_branches_cover_empty_inputs_and_missing_ui_context():
    modules = load_suzanne_modules()
    common = modules.common

    assert common._clean_markdown(None) == ""
    assert common._tail_lines(None, 3) == ""
    assert common._merge_tail_lines("one", "two", 0) == ""
    assert common._merge_tail_lines("", "   ", 5) == ""

    common.bpy.context.window_manager.windows = [
        SimpleNamespace(screen=None),
        SimpleNamespace(screen=SimpleNamespace(areas=[SimpleNamespace(type="VIEW_3D", regions=[])])),
    ]
    assert common._find_area_context("INFO") is None

    class BrokenSpaces:
        @property
        def active(self):
            raise RuntimeError("boom")

    common._enable_info_filters(SimpleNamespace(spaces=BrokenSpaces()))
    common._enable_info_filters(SimpleNamespace(spaces=SimpleNamespace(active=None)))


def test_common_info_history_helpers_cover_remaining_error_paths():
    modules = load_suzanne_modules()
    common = modules.common
    logs = []

    class ExplodingArea:
        def __init__(self):
            self._type = "VIEW_3D"
            self.regions = [SimpleNamespace(type="WINDOW")]

        @property
        def type(self):
            return self._type

        @type.setter
        def type(self, value):
            if value == "INFO":
                raise RuntimeError("boom")
            self._type = value

    class ResetFailArea:
        def __init__(self):
            self._type = "VIEW_3D"
            self.regions = []
            self._fail_reset = False

        @property
        def type(self):
            return self._type

        @type.setter
        def type(self, value):
            if value == "INFO":
                self._type = value
                self._fail_reset = True
                return
            if self._fail_reset and value == "VIEW_3D":
                raise RuntimeError("reset boom")
            self._type = value

    with mock.patch.object(common, "_log", side_effect=logs.append):
        common.bpy.context.window_manager.windows = [
            SimpleNamespace(screen=SimpleNamespace(areas=[ExplodingArea()]))
        ]
        assert common._copy_info_reports_with_temp_area() == ""

        common.bpy.context.window_manager.windows = [
            SimpleNamespace(screen=SimpleNamespace(areas=[ResetFailArea()]))
        ]
        assert common._copy_info_reports_with_temp_area() == ""

        common.bpy.context.window_manager.clipboard = "keep"
        with mock.patch.object(common, "_find_area_context", return_value={"area": object()}):
            with mock.patch.object(
                common,
                "_copy_info_reports_with_override",
                side_effect=RuntimeError("copy failed"),
            ):
                with mock.patch.object(common, "_copy_info_reports_with_temp_area", return_value=""):
                    with mock.patch.object(common, "_operator_snapshot_lines", return_value=""):
                        assert common._get_info_history_lines(limit=2) == ""

    assert common.bpy.context.window_manager.clipboard == "keep"
    assert any("Could not copy INFO history via temp area" in message for message in logs)
    assert any("Could not copy INFO history:" in message for message in logs)


def test_common_operator_snapshot_covers_skip_and_fallback_property_paths():
    modules = load_suzanne_modules()
    common = modules.common

    class BrokenDefaultProperty:
        identifier = "value"
        is_readonly = False

        @property
        def default(self):
            raise RuntimeError("no default")

    class BrokenValueOperator:
        bl_idname = "mesh.broken_value"
        bl_rna = SimpleNamespace(
            properties=[SimpleNamespace(identifier="value", is_readonly=False, default="x")]
        )

        @property
        def value(self):
            raise RuntimeError("boom")

    common.bpy.context.window_manager.operators = [
        SimpleNamespace(bl_idname="", bl_rna=SimpleNamespace(identifier="", properties=[])),
        BrokenValueOperator(),
        SimpleNamespace(
            bl_idname="mesh.empty",
            bl_rna=SimpleNamespace(
                properties=[SimpleNamespace(identifier="value", is_readonly=False, default="x")]
            ),
            value="",
        ),
        SimpleNamespace(
            bl_idname="mesh.same_default",
            bl_rna=SimpleNamespace(
                properties=[SimpleNamespace(identifier="value", is_readonly=False, default="same")]
            ),
            value="same",
        ),
        SimpleNamespace(
            bl_idname="mesh.fallback_default",
            bl_rna=SimpleNamespace(properties=[BrokenDefaultProperty()]),
            value="custom",
        ),
        SimpleNamespace(
            bl_idname="mesh.no_props",
            bl_rna=SimpleNamespace(
                properties=[SimpleNamespace(identifier="rna_type", is_readonly=False, default=None)]
            ),
        ),
    ]

    assert common._operator_snapshot_lines(10) == (
        "mesh.broken_value\n"
        "mesh.empty\n"
        "mesh.same_default\n"
        "mesh.fallback_default(value='custom')\n"
        "mesh.no_props"
    )


def test_common_audio_and_preference_helpers_cover_remaining_fallback_branches():
    modules = load_suzanne_modules()
    common = modules.common

    with mock.patch.object(common, "_get_json", side_effect=RuntimeError("offline")):
        assert common._get_models_from_api("sk-live") == []

    prefs = make_preferences()
    context = make_context(common.ADDON_MODULE, prefs=prefs)
    with mock.patch.object(common, "_get_addon_preferences", return_value=prefs):
        with mock.patch.object(common, "_get_models_cached", return_value=["base-model"]):
            assert common._transcribe_model_enum_items(None, context) == [
                ("gpt-4o-mini-transcribe", "gpt-4o-mini-transcribe", ""),
                ("whisper-1", "whisper-1", ""),
            ]

    with mock.patch.object(common.shutil, "which", return_value="arecord"):
        with mock.patch.object(common.subprocess, "Popen", side_effect=RuntimeError("boom")):
            assert common._get_audio_devices_linux() == [("default", "default", "default")]

    class SplitLinesOnly:
        def __init__(self, lines):
            self._lines = lines

        def splitlines(self):
            return self._lines

    linux_proc = SimpleNamespace(
        communicate=lambda timeout: (SplitLinesOnly([123, b" ", b"null"]), b"")
    )
    with mock.patch.object(common.shutil, "which", return_value="arecord"):
        with mock.patch.object(common.subprocess, "Popen", return_value=linux_proc):
            assert common._get_audio_devices_linux() == [("default", "default", "default")]

    with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
        with mock.patch.object(common.subprocess, "Popen", side_effect=RuntimeError("boom")):
            assert common._get_audio_devices_windows() == [("default", "default", "default")]

    windows_proc = SimpleNamespace(
        communicate=lambda timeout: (b"", SplitLinesOnly([123]))
    )
    with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
        with mock.patch.object(common.subprocess, "Popen", return_value=windows_proc):
            assert common._get_audio_devices_windows() == [("default", "default", "default")]

    alt_name_proc = SimpleNamespace(
        communicate=lambda timeout: (b"", b'DirectShow audio devices\nAlternative name "alias"\n')
    )
    with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
        with mock.patch.object(common.subprocess, "Popen", return_value=alt_name_proc):
            assert common._get_audio_devices_windows() == [("default", "default", "default")]

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = pathlib.Path(tmpdir)
        with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
            assert common._get_audio_devices_macos() == [("default", "default", "default")]

        atunc_path = addon_dir / "atunc" / "atunc"
        atunc_path.parent.mkdir(parents=True, exist_ok=True)
        atunc_path.write_text("", encoding="utf-8")

        bad_macos_proc = SimpleNamespace(communicate=lambda timeout: (b"not-json", b""))
        with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
            with mock.patch.object(common.subprocess, "Popen", return_value=bad_macos_proc):
                assert common._get_audio_devices_macos() == [("default", "default", "default")]

        empty_macos_proc = SimpleNamespace(communicate=lambda timeout: (b"[]", b""))
        with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
            with mock.patch.object(common.subprocess, "Popen", return_value=empty_macos_proc):
                assert common._get_audio_devices_macos() == [("default", "default", "default")]

    assert common._first_non_default_audio_device(
        [("", "", ""), (None, "", ""), ("default", "default", "default")]
    ) == ""

    with mock.patch.object(common.platform, "system", return_value="Windows"):
        assert common._os_display_name() == "Windows"

    class BrokenContext:
        @property
        def preferences(self):
            raise RuntimeError("boom")

    assert common._get_addon_preferences(BrokenContext()) is None
    assert common._get_effective_api_key(None) == ""
    common._set_diagnostics_message(None, message="ignored", error="ignored")


def test_common_info_history_helpers_cover_remaining_guard_branches():
    modules = load_suzanne_modules()
    common = modules.common
    logs = []

    class SetterLockedSpace:
        def __init__(self):
            self.show_report_info = False
            self.show_report_operator = False
            self.show_report_warning = False
            self.show_report_error = False

        @property
        def show_report_debug(self):
            return False

        @show_report_debug.setter
        def show_report_debug(self, _value):
            raise RuntimeError("locked")

    locked_space = SetterLockedSpace()
    common._enable_info_filters(SimpleNamespace(spaces=SimpleNamespace(active=locked_space)))
    assert locked_space.show_report_info is True
    assert locked_space.show_report_operator is True
    assert locked_space.show_report_warning is True
    assert locked_space.show_report_error is True

    common.bpy.context.window_manager.windows = [
        SimpleNamespace(screen=None),
        SimpleNamespace(screen=SimpleNamespace(areas=[])),
    ]
    assert common._copy_info_reports_with_temp_area() == ""

    class BrokenOperators:
        def __iter__(self):
            raise RuntimeError("boom")

    with mock.patch.object(common, "_log", side_effect=logs.append):
        common.bpy.context.window_manager.operators = BrokenOperators()
        assert common._operator_snapshot_lines(5) == ""

    assert any("Operator fallback failed" in message for message in logs)


def test_common_probe_helpers_cover_remaining_platform_and_cleanup_paths():
    modules = load_suzanne_modules()
    common = modules.common

    with mock.patch.object(common.platform, "system", return_value="Linux"):
        linux_candidates = common._microphone_probe_candidates("ffmpeg", "probe.wav")
    assert linux_candidates[0][:5] == ["ffmpeg", "-nostdin", "-f", "alsa", "-i"]
    assert linux_candidates[1][:5] == ["ffmpeg", "-nostdin", "-f", "pulse", "-i"]

    with mock.patch.object(common.platform, "system", return_value="Plan9"):
        fallback_candidates = common._microphone_probe_candidates("ffmpeg", "probe.wav")
    assert fallback_candidates == [
        ["ffmpeg", "-nostdin", "-f", "alsa", "-i", "default", "-t", "0.40", "-ac", "1", "-ar", "16000", "-y", "probe.wav"]
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = pathlib.Path(tmpdir)
        with mock.patch.object(common.platform, "system", return_value="Darwin"):
            with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
                ok, detail = common._run_microphone_probe()
        assert ok is False
        assert detail == "atunc is not installed."

        atunc_path = addon_dir / "atunc" / "atunc"
        atunc_path.parent.mkdir(parents=True, exist_ok=True)
        atunc_path.write_text("", encoding="utf-8")

        with mock.patch.object(common.platform, "system", return_value="Darwin"):
            with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
                with mock.patch.object(common, "_get_audio_devices_macos", return_value=[]):
                    ok, detail = common._run_microphone_probe()
        assert ok is False
        assert detail == "No macOS audio devices were detected."

        with mock.patch.object(common.platform, "system", return_value="Darwin"):
            with mock.patch.object(common, "_addon_dir", return_value=addon_dir):
                with mock.patch.object(
                    common,
                    "_get_audio_devices_macos",
                    return_value=[("7", "Built-in Mic", "Built-in Mic")],
                ):
                    ok, detail = common._run_microphone_probe()
        assert ok is True
        assert detail == "atunc found with 1 detected device(s)."

    with tempfile.TemporaryDirectory() as tmpdir:
        probe_path = pathlib.Path(tmpdir) / "probe.wav"
        probe_path.write_bytes(b"")

        class TempHandle:
            def __enter__(self):
                return SimpleNamespace(name=str(probe_path))

            def __exit__(self, exc_type, exc, tb):
                return False

        with mock.patch.object(common.platform, "system", return_value="Windows"):
            with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
                with mock.patch.object(common.tempfile, "NamedTemporaryFile", return_value=TempHandle()):
                    with mock.patch.object(common, "_microphone_probe_candidates", return_value=[["ffmpeg"]]):
                        with mock.patch.object(common.subprocess, "run", side_effect=RuntimeError("boom")):
                            ok, detail = common._run_microphone_probe()
        assert ok is False
        assert detail == "boom"
        if probe_path.exists():
            probe_path.unlink()

        probe_path.write_bytes(b"")
        with mock.patch.object(common.platform, "system", return_value="Windows"):
            with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
                with mock.patch.object(common.tempfile, "NamedTemporaryFile", return_value=TempHandle()):
                    with mock.patch.object(common, "_microphone_probe_candidates", return_value=[["ffmpeg"]]):
                        with mock.patch.object(
                            common.subprocess,
                            "run",
                            return_value=SimpleNamespace(returncode=1, stderr=b"probe failed\n"),
                        ):
                            with mock.patch.object(common.os, "remove", side_effect=OSError("locked")):
                                ok, detail = common._run_microphone_probe()
        assert ok is False
        assert detail == "probe failed"
        if probe_path.exists():
            probe_path.unlink()

        probe_path.write_bytes(b"")
        with mock.patch.object(common.platform, "system", return_value="Windows"):
            with mock.patch.object(common, "_resolve_ffmpeg_path", return_value="ffmpeg"):
                with mock.patch.object(common.tempfile, "NamedTemporaryFile", return_value=TempHandle()):
                    with mock.patch.object(common, "_microphone_probe_candidates", return_value=[["ffmpeg"]]):
                        with mock.patch.object(
                            common.subprocess,
                            "run",
                            return_value=SimpleNamespace(returncode=0, stderr=b""),
                        ):
                            with mock.patch.object(common.os.path, "getsize", return_value=100):
                                ok, detail = common._run_microphone_probe()
        assert ok is True
        assert detail == "Microphone capture probe succeeded."
        if probe_path.exists():
            probe_path.unlink()


def test_common_storage_and_conversation_helpers_cover_remaining_error_paths():
    modules = load_suzanne_modules()
    common = modules.common
    logs = []

    class FailingDir:
        def mkdir(self, *args, **kwargs):
            raise OSError("nope")

    with mock.patch.object(common, "_recordings_dir", return_value=FailingDir()):
        with mock.patch.object(common, "_log", side_effect=logs.append):
            assert common._ensure_recordings_dir() is False

    class FailingAddonPath:
        def __truediv__(self, _name):
            return self

        def mkdir(self, *args, **kwargs):
            raise OSError("nope")

    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch.object(common, "_addon_dir", return_value=FailingAddonPath()):
            with mock.patch.object(common.tempfile, "gettempdir", return_value=tmpdir):
                with mock.patch.object(common, "_log", side_effect=logs.append):
                    fallback_dir = common._conversation_storage_dir()
    assert fallback_dir.name == "suzanne_va_data"

    assert common._clip_text("", 10) == ""

    class FixedDateTime:
        @classmethod
        def now(cls):
            return cls()

        def strftime(self, _fmt):
            return "2026-03-03 20:00"

    with mock.patch.object(common.datetime, "datetime", FixedDateTime):
        assert common._conversation_title_from_seed("") == "Conversation 2026-03-03 20:00"

    assert common._normalize_conversation(None) is None
    assert common._normalize_conversation({"id": ""}) is None

    class ReadFailPath:
        def exists(self):
            return True

        def read_text(self, encoding):
            raise ValueError("bad json")

    with mock.patch.object(common, "_conversation_store_path", return_value=ReadFailPath()):
        with mock.patch.object(common, "_log", side_effect=logs.append):
            assert common._load_conversation_store() == common._empty_conversation_store()

    class NonDictPath:
        def exists(self):
            return True

        def read_text(self, encoding):
            return "[]"

    with mock.patch.object(common, "_conversation_store_path", return_value=NonDictPath()):
        assert common._load_conversation_store() == common._empty_conversation_store()

    class TmpFailPath:
        def __init__(self):
            self.suffix = ".json"
            self.tmp = self

        def with_suffix(self, _suffix):
            return self.tmp

        def write_text(self, *args, **kwargs):
            raise OSError("disk full")

        def exists(self):
            return True

        def unlink(self):
            raise OSError("locked")

    with mock.patch.object(common, "_conversation_store_path", return_value=TmpFailPath()):
        with mock.patch.object(common, "_log", side_effect=logs.append):
            assert common._save_conversation_store({"conversations": []}) is False

    assert common._find_conversation({"conversations": []}, "") is None

    class LockedScene:
        @property
        def suzanne_va_active_conversation(self):
            return ""

        @suzanne_va_active_conversation.setter
        def suzanne_va_active_conversation(self, _value):
            raise RuntimeError("locked")

    common._set_active_conversation(LockedScene(), "abc")

    no_conv_scene = SimpleNamespace(suzanne_va_active_conversation=common._NO_CONVERSATION_ID)
    assert common._sync_active_conversation(no_conv_scene, {"conversations": []}) == common._NO_CONVERSATION_ID

    empty_scene = SimpleNamespace(suzanne_va_active_conversation="")
    assert common._sync_active_conversation(empty_scene, {"conversations": []}) == common._NO_CONVERSATION_ID
    assert empty_scene.suzanne_va_active_conversation == common._NO_CONVERSATION_ID

    create_scene = SimpleNamespace(suzanne_va_active_conversation="")
    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        with mock.patch.object(common, "_sync_active_conversation", return_value=common._NO_CONVERSATION_ID):
            with mock.patch.object(common, "_save_conversation_store", return_value=False):
                with mock.patch.object(common, "_now_iso_timestamp", return_value="2026-03-03T20:00:00"):
                    with mock.patch.object(common.uuid, "uuid4", return_value=SimpleNamespace(hex="abc123")):
                        conversation, store = common._get_active_conversation(
                            create_scene,
                            create_if_missing=True,
                            title_seed="Hello",
                        )
    assert conversation["id"] == "abc123"
    assert len(store["conversations"]) == 1

    with mock.patch.object(
        common,
        "_load_conversation_store",
        return_value={
            "conversations": [
                {"id": " ", "title": "Hidden", "messages": [], "updated_at": ""},
                {"id": "abc", "title": "Shown", "messages": [], "updated_at": ""},
            ]
        },
    ):
        enum_items = common._conversation_enum_items(None, None)
    assert len(enum_items) == 2
    assert enum_items[1][0] == "abc"

    disabled_scene = SimpleNamespace(suzanne_va_use_conversation_context=False)
    assert common._conversation_context_block(disabled_scene) == ""

    enabled_scene = SimpleNamespace(suzanne_va_use_conversation_context=True, suzanne_va_context_turns=1)
    with mock.patch.object(common, "_get_active_conversation", return_value=(None, {})):
        assert common._conversation_context_block(enabled_scene) == ""
    with mock.patch.object(
        common,
        "_get_active_conversation",
        return_value=({"messages": [{"role": "user", "text": "   "}]}, {}),
    ):
        assert common._conversation_context_block(enabled_scene) == ""

    with mock.patch.object(common, "_get_addon_preferences", return_value=None):
        with mock.patch.object(common, "_get_active_conversation", return_value=(None, {})):
            assert common._append_conversation_exchange(SimpleNamespace(), "User", "Assistant", "text") is False

    long_messages = [
        {"role": "user", "text": f"Message {index}", "source": "text", "timestamp": "t"}
        for index in range(401)
    ]
    trimmed_conversation = {"title": "", "messages": list(long_messages)}
    with mock.patch.object(common, "_get_addon_preferences", return_value=None):
        with mock.patch.object(common, "_get_active_conversation", return_value=(trimmed_conversation, {"conversations": []})):
            with mock.patch.object(common, "_now_iso_timestamp", return_value="2026-03-03T20:00:00"):
                with mock.patch.object(common, "_save_conversation_store", return_value=True):
                    assert common._append_conversation_exchange(SimpleNamespace(), "User", "Assistant", "text") is True
    assert len(trimmed_conversation["messages"]) == 400

    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        with mock.patch.object(common, "_save_conversation_store", return_value=False):
            with mock.patch.object(common, "_now_iso_timestamp", return_value="2026-03-03T20:00:00"):
                with mock.patch.object(common.uuid, "uuid4", return_value=SimpleNamespace(hex="new123")):
                    assert common._new_conversation(SimpleNamespace(), title_seed="Hello") is None

    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        assert common._rename_conversation(SimpleNamespace(suzanne_va_active_conversation=""), "Title") is False
    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        assert common._rename_conversation(SimpleNamespace(suzanne_va_active_conversation="abc"), "Title") is False
    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": [{"id": "abc"}]}):
        with mock.patch.object(common, "_find_conversation", return_value={"id": "abc"}):
            assert common._rename_conversation(SimpleNamespace(suzanne_va_active_conversation="abc"), "   ") is False

    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        assert common._delete_active_conversation(SimpleNamespace(suzanne_va_active_conversation="")) is False
    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        assert common._delete_active_conversation(SimpleNamespace(suzanne_va_active_conversation="abc")) is False
    with mock.patch.object(
        common,
        "_load_conversation_store",
        return_value={"conversations": [{"id": "abc"}]},
    ):
        with mock.patch.object(common, "_save_conversation_store", return_value=False):
            assert common._delete_active_conversation(SimpleNamespace(suzanne_va_active_conversation="abc")) is False

    with mock.patch.object(common, "_get_active_conversation", return_value=(None, {})):
        assert common._conversation_preview_lines(SimpleNamespace()) == []
    with mock.patch.object(common, "_get_active_conversation", return_value=({"messages": []}, {})):
        assert common._conversation_preview_lines(SimpleNamespace()) == []

    class TextHttpError:
        def read(self):
            return "plain text"

    assert common._read_http_error_body(TextHttpError()) == "plain text"

    with mock.patch.object(common.mimetypes, "guess_type", return_value=(None, None)):
        with mock.patch.object(common, "_read_file_bytes", return_value=b"abc"):
            with mock.patch.object(common, "_post_multipart", return_value='{"text": ""}') as post_multipart:
                common._transcribe_audio("sk-live", "whisper-1", "recording.unknown")
    files_arg = post_multipart.call_args.args[3]
    assert files_arg["file"][1] == "audio/wav"

    assert any("Could not create recordings dir" in message for message in logs)
    assert any("Could not create data dir" in message for message in logs)
    assert any("Could not read conversations file" in message for message in logs)
    assert any("Could not save conversations file" in message for message in logs)


def test_common_path_and_creation_helpers_cover_remaining_success_paths():
    modules = load_suzanne_modules()
    common = modules.common

    addon_dir = common._addon_dir()
    assert addon_dir.name == "suzanne"
    assert common._recordings_dir() == addon_dir / "recordings"

    with tempfile.TemporaryDirectory() as tmpdir:
        recordings_dir = pathlib.Path(tmpdir) / "recordings"
        with mock.patch.object(common, "_recordings_dir", return_value=recordings_dir):
            assert common._ensure_recordings_dir() is True
        assert recordings_dir.exists()

    class FixedDateTime:
        @classmethod
        def now(cls):
            return cls()

        def strftime(self, _fmt):
            return "2026-03-03_20-00-00"

    with mock.patch.object(common.datetime, "datetime", FixedDateTime):
        assert common._now_timestamp() == "2026-03-03_20-00-00"

    scene = SimpleNamespace(suzanne_va_active_conversation="")
    with mock.patch.object(common, "_load_conversation_store", return_value={"conversations": []}):
        with mock.patch.object(common, "_sync_active_conversation", return_value=common._NO_CONVERSATION_ID):
            with mock.patch.object(common, "_save_conversation_store", return_value=True):
                with mock.patch.object(common, "_now_iso_timestamp", return_value="2026-03-03T20:00:00"):
                    with mock.patch.object(common.uuid, "uuid4", return_value=SimpleNamespace(hex="saved123")):
                        with mock.patch.object(common, "_set_active_conversation") as set_active:
                            conversation, store = common._get_active_conversation(
                                scene,
                                create_if_missing=True,
                                title_seed="Hello",
                            )

    assert conversation["id"] == "saved123"
    assert len(store["conversations"]) == 1
    set_active.assert_called_once_with(scene, "saved123")
