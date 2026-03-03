import json
import pathlib
import tempfile
from types import SimpleNamespace
from unittest import mock

from tests.test_support import load_suzanne_modules, make_context, make_preferences, make_scene


def test_send_message_execute_rejects_blank_prompt():
    modules = load_suzanne_modules()
    context = make_context(modules.common.ADDON_MODULE, scene=make_scene(suzanne_va_prompt="   "))
    operator = modules.operators.SUZANNEVA_OT_send_message()

    result = operator.execute(context)

    assert result == {"CANCELLED"}
    assert operator._reports[-1][1] == "Please type a message first."


def test_send_message_execute_updates_scene_and_saves_history_on_success():
    modules = load_suzanne_modules()
    scene = make_scene(
        suzanne_va_prompt="How do I bevel an edge?",
        suzanne_va_include_info_history=True,
    )
    prefs = make_preferences()
    context = make_context(modules.common.ADDON_MODULE, scene=scene, prefs=prefs)
    operator = modules.operators.SUZANNEVA_OT_send_message()

    with mock.patch.object(modules.operators, "_get_info_history_lines", return_value="INFO LOG"):
        with mock.patch.object(
            modules.operators,
            "_conversation_context_block",
            return_value="## Previous Conversation Context",
        ):
            with mock.patch.object(modules.operators, "_build_markdown_input", return_value="BUILT"):
                with mock.patch.object(
                    modules.operators,
                    "_blender_only_prefix",
                    side_effect=lambda text: f"PREFIX::{text}",
                ):
                    with mock.patch.object(
                        modules.operators,
                        "_call_chatgpt",
                        return_value={"output_text": "Use the bevel tool."},
                    ) as call_chatgpt:
                        with mock.patch.object(modules.operators, "_append_conversation_exchange") as append_exchange:
                            with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
                                result = operator.execute(context)

    assert result == {"FINISHED"}
    assert scene.suzanne_va_status == "Idle (sent)"
    assert scene.suzanne_va_last_info_history == "INFO LOG"
    assert scene.suzanne_va_last_transcript == "How do I bevel an edge?"
    assert scene.suzanne_va_last_response == "Use the bevel tool."
    assert scene.suzanne_va_expand_transcript is False
    assert scene.suzanne_va_expand_response is False
    assert redraw.call_count == 2
    call_chatgpt.assert_called_once_with("sk-test", "gpt-4o-mini", "PREFIX::BUILT")
    append_exchange.assert_called_once_with(
        scene,
        "How do I bevel an edge?",
        "Use the bevel tool.",
        source="text",
    )


def test_send_message_execute_handles_network_failure():
    modules = load_suzanne_modules()
    scene = make_scene(suzanne_va_prompt="Hello")
    context = make_context(modules.common.ADDON_MODULE, scene=scene, prefs=make_preferences())
    operator = modules.operators.SUZANNEVA_OT_send_message()

    with mock.patch.object(modules.operators, "_conversation_context_block", return_value=""):
        with mock.patch.object(modules.operators, "_build_markdown_input", return_value="BUILT"):
            with mock.patch.object(modules.operators, "_blender_only_prefix", return_value="PREFIX::BUILT"):
                with mock.patch.object(
                    modules.operators,
                    "_call_chatgpt",
                    side_effect=modules.operators.URLError("offline"),
                ):
                    with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
                        result = operator.execute(context)

    assert result == {"CANCELLED"}
    assert scene.suzanne_va_status == "Idle (error)"
    assert redraw.call_count == 2
    assert "Send failed" in operator._reports[-1][1]


def test_test_api_key_execute_rejects_empty_keys():
    modules = load_suzanne_modules()
    prefs = make_preferences(api_key="")
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)
    operator = modules.operators.SUZANNEVA_OT_test_api_key()

    with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
        result = operator.execute(context)

    assert result == {"CANCELLED"}
    set_diag.assert_called_once_with(prefs, error="OpenAI API key is empty.")


def test_test_api_key_execute_rejects_bad_key_prefix():
    modules = load_suzanne_modules()
    prefs = make_preferences(api_key="not-valid")
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)
    operator = modules.operators.SUZANNEVA_OT_test_api_key()

    with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
        with mock.patch.object(modules.operators, "_get_json") as get_json:
            result = operator.execute(context)

    assert result == {"CANCELLED"}
    assert get_json.call_count == 0
    set_diag.assert_called_once_with(
        prefs,
        error="OpenAI API key must start with 'sk-'.",
    )


def test_test_api_key_execute_accepts_valid_json_response():
    modules = load_suzanne_modules()
    prefs = make_preferences(api_key="sk-live")
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)
    operator = modules.operators.SUZANNEVA_OT_test_api_key()

    with mock.patch.object(modules.operators, "_get_json", return_value='{"data": []}') as get_json:
        with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
            result = operator.execute(context)

    assert result == {"FINISHED"}
    get_json.assert_called_once_with("https://api.openai.com/v1/models", "sk-live")
    set_diag.assert_called_once_with(prefs, message="API key is valid.")


def test_microphone_press_execute_starts_recording_and_updates_status():
    modules = load_suzanne_modules()
    scene = make_scene(suzanne_va_mic_active=False)
    context = make_context(modules.common.ADDON_MODULE, scene=scene)
    operator = modules.operators.SUZANNEVA_OT_microphone_press()

    with mock.patch.object(operator, "_start_recording", return_value=True):
        with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
            result = operator.execute(context)

    assert result == {"FINISHED"}
    assert scene.suzanne_va_mic_active is True
    assert scene.suzanne_va_status == "Recording..."
    assert redraw.call_count == 1
    assert operator._reports[-1][1] == "Suzanne VA: Recording started"


def test_microphone_press_execute_cancels_when_recording_cannot_start():
    modules = load_suzanne_modules()
    scene = make_scene(suzanne_va_mic_active=False)
    context = make_context(modules.common.ADDON_MODULE, scene=scene)
    operator = modules.operators.SUZANNEVA_OT_microphone_press()

    with mock.patch.object(operator, "_start_recording", return_value=False):
        with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
            result = operator.execute(context)

    assert result == {"CANCELLED"}
    assert scene.suzanne_va_mic_active is False
    assert scene.suzanne_va_status == "Idle"
    assert redraw.call_count == 1


def test_clear_saved_api_key_and_copy_last_error_update_preferences_and_clipboard():
    modules = load_suzanne_modules()
    prefs = make_preferences(
        api_key="sk-live",
        show_api_key=True,
        diagnostics_last_error="Copy this.",
    )
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)

    clear_operator = modules.operators.SUZANNEVA_OT_clear_saved_api_key()
    with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
        clear_result = clear_operator.execute(context)

    copy_operator = modules.operators.SUZANNEVA_OT_copy_last_error()
    copy_result = copy_operator.execute(context)

    assert clear_result == {"FINISHED"}
    assert prefs.api_key == ""
    assert prefs.show_api_key is False
    set_diag.assert_called_once_with(prefs, message="Saved API key cleared.")
    assert copy_result == {"FINISHED"}
    assert context.window_manager.clipboard == "Copy this."


def test_conversation_operators_delegate_to_storage_helpers():
    modules = load_suzanne_modules()
    scene = make_scene(suzanne_va_prompt="Start here")
    context = make_context(modules.common.ADDON_MODULE, scene=scene)

    new_operator = modules.operators.SUZANNEVA_OT_new_conversation()
    rename_operator = modules.operators.SUZANNEVA_OT_rename_conversation()
    rename_operator.new_title = "Renamed conversation"
    delete_operator = modules.operators.SUZANNEVA_OT_delete_conversation()

    with mock.patch.object(
        modules.operators,
        "_new_conversation",
        return_value={"title": "New conversation"},
    ) as new_conversation:
        with mock.patch.object(modules.operators, "_rename_conversation", return_value=True) as rename_conversation:
            with mock.patch.object(
                modules.operators,
                "_delete_active_conversation",
                return_value=True,
            ) as delete_conversation:
                with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
                    new_result = new_operator.execute(context)
                    rename_result = rename_operator.execute(context)
                    delete_result = delete_operator.execute(context)

    assert new_result == {"FINISHED"}
    assert rename_result == {"FINISHED"}
    assert delete_result == {"FINISHED"}
    new_conversation.assert_called_once_with(scene, title_seed="Start here")
    rename_conversation.assert_called_once_with(scene, "Renamed conversation")
    delete_conversation.assert_called_once_with(scene)
    assert redraw.call_count == 3


def test_simple_operators_cover_refresh_and_recordings_folder_paths():
    modules = load_suzanne_modules()
    prefs = make_preferences()
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)

    refresh_models = modules.operators.SUZANNEVA_OT_refresh_models()
    with mock.patch.object(modules.operators, "_get_models_cached") as get_models:
        with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
            assert refresh_models.execute(context) == {"FINISHED"}
    get_models.assert_called_once_with("sk-test", force=True)
    set_diag.assert_called_once_with(prefs, message="Model list refreshed.")

    modules.operators._AUDIO_DEVICES_CACHE["ts"] = 99.0
    modules.operators._AUDIO_DEVICES_CACHE["items"] = [("x", "x", "x")]
    refresh_devices = modules.operators.SUZANNEVA_OT_refresh_devices()
    assert refresh_devices.execute(context) == {"FINISHED"}
    assert modules.operators._AUDIO_DEVICES_CACHE["ts"] == 0.0
    assert modules.operators._AUDIO_DEVICES_CACHE["items"] == []

    open_folder = modules.operators.SUZANNEVA_OT_open_recordings_folder()
    with mock.patch.object(modules.operators, "_ensure_recordings_dir") as ensure_dir:
        with mock.patch.object(modules.operators, "_recordings_dir", return_value="C:/temp/recordings"):
            with mock.patch.object(modules.operators, "_show_file_in_os", return_value=True):
                assert open_folder.execute(context) == {"FINISHED"}
    assert ensure_dir.call_count == 1

    with mock.patch.object(modules.operators, "_ensure_recordings_dir"):
        with mock.patch.object(modules.operators, "_recordings_dir", return_value="C:/temp/recordings"):
            with mock.patch.object(modules.operators, "_show_file_in_os", return_value=False):
                assert open_folder.execute(context) == {"CANCELLED"}


def test_diagnostics_operators_cover_microphone_and_transcription_paths():
    modules = load_suzanne_modules()
    prefs = make_preferences()
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)

    test_microphone = modules.operators.SUZANNEVA_OT_test_microphone()
    with mock.patch.object(modules.operators, "_run_microphone_probe", return_value=(False, "No mic")):
        with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
            assert test_microphone.execute(context) == {"CANCELLED"}
    set_diag.assert_called_once_with(prefs, error="Microphone test failed: No mic")

    with mock.patch.object(modules.operators, "_run_microphone_probe", return_value=(True, "OK")):
        with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
            assert test_microphone.execute(context) == {"FINISHED"}
    set_diag.assert_called_once_with(prefs, message="Microphone test passed: OK")

    missing_key_context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(api_key=""))
    test_transcription = modules.operators.SUZANNEVA_OT_test_transcription()
    with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
        assert test_transcription.execute(missing_key_context) == {"CANCELLED"}
    set_diag.assert_called_once()

    valid_context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(api_key="sk-live"))
    with mock.patch.object(modules.operators, "_write_silence_wav") as write_silence:
        with mock.patch.object(modules.operators, "_transcribe_audio", return_value={"text": "hello world"}):
            with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
                assert test_transcription.execute(valid_context) == {"FINISHED"}
    assert write_silence.call_count == 1
    set_diag.assert_called_once()
    assert "Transcription test passed." in set_diag.call_args.kwargs["message"]


def test_microphone_press_execute_stop_flow_covers_missing_file_and_success_send():
    modules = load_suzanne_modules()

    error_scene = make_scene(suzanne_va_mic_active=True)
    error_context = make_context(modules.common.ADDON_MODULE, scene=error_scene)
    error_operator = modules.operators.SUZANNEVA_OT_microphone_press()
    modules.operators.SUZANNEVA_OT_microphone_press.recording_path = "missing.wav"

    with mock.patch.object(error_operator, "_stop_recording") as stop_recording:
        with mock.patch.object(error_operator, "_wait_for_file", return_value=False):
            with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
                assert error_operator.execute(error_context) == {"FINISHED"}
    assert stop_recording.call_count == 1
    assert error_scene.suzanne_va_mic_active is False
    assert error_scene.suzanne_va_status == "Idle (error)"
    assert redraw.call_count == 2

    success_scene = make_scene(suzanne_va_mic_active=True)
    success_context = make_context(modules.common.ADDON_MODULE, scene=success_scene)
    success_operator = modules.operators.SUZANNEVA_OT_microphone_press()
    modules.operators.SUZANNEVA_OT_microphone_press.recording_path = "recording.wav"

    with mock.patch.object(success_operator, "_stop_recording") as stop_recording:
        with mock.patch.object(success_operator, "_wait_for_file", return_value=True):
            with mock.patch.object(success_operator, "_send_to_chatgpt", return_value=(True, "")):
                with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
                    assert success_operator.execute(success_context) == {"FINISHED"}
    assert stop_recording.call_count == 1
    assert success_scene.suzanne_va_mic_active is False
    assert success_scene.suzanne_va_status == "Idle (sent)"
    assert redraw.call_count == 2


def test_conversation_dialog_operators_cover_invoke_paths():
    modules = load_suzanne_modules()
    context = make_context(modules.common.ADDON_MODULE, scene=make_scene())

    rename_operator = modules.operators.SUZANNEVA_OT_rename_conversation()
    with mock.patch.object(modules.operators, "_get_active_conversation", return_value=(None, {})):
        assert rename_operator.invoke(context, None) == {"CANCELLED"}

    with mock.patch.object(
        modules.operators,
        "_get_active_conversation",
        return_value=({"title": "Current title"}, {}),
    ):
        assert rename_operator.invoke(context, None) == "DIALOG"
    assert rename_operator.new_title == "Current title"

    delete_operator = modules.operators.SUZANNEVA_OT_delete_conversation()
    assert delete_operator.invoke(context, object()) == "CONFIRM"


def test_microphone_helper_methods_cover_paths_processes_and_waits():
    modules = load_suzanne_modules()
    operator = modules.operators.SUZANNEVA_OT_microphone_press()

    with mock.patch.object(modules.operators, "_resolve_ffmpeg_path", return_value="ffmpeg-bin"):
        assert operator._ffmpeg_path() == "ffmpeg-bin"

    with tempfile.TemporaryDirectory() as tmpdir:
        addon_dir = pathlib.Path(tmpdir)
        atunc_path = addon_dir / "atunc" / "atunc"
        atunc_path.parent.mkdir(parents=True, exist_ok=True)
        atunc_path.write_text("", encoding="utf-8")

        with mock.patch.object(modules.operators, "_addon_dir", return_value=addon_dir):
            assert operator._atunc_path() == str(atunc_path)

        with mock.patch.object(modules.operators, "_addon_dir", return_value=addon_dir / "missing-root"):
            assert operator._atunc_path() is None

    context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(file_prefix="clip_"))
    with mock.patch.object(modules.operators, "_get_addon_preferences", return_value=context.preferences.addons[modules.common.ADDON_MODULE].preferences):
        with mock.patch.object(modules.operators, "_ensure_recordings_dir", return_value=True):
            with mock.patch.object(modules.operators, "_recordings_dir", return_value=pathlib.Path("C:/recordings")):
                with mock.patch.object(modules.operators, "_now_timestamp", return_value="2026-03-03_20-00-00"):
                    assert operator._get_recording_path(context).endswith("clip_2026-03-03_20-00-00.wav")

    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch.object(modules.operators, "_get_addon_preferences", return_value=context.preferences.addons[modules.common.ADDON_MODULE].preferences):
            with mock.patch.object(modules.operators, "_ensure_recordings_dir", return_value=False):
                with mock.patch.object(modules.operators.tempfile, "gettempdir", return_value=tmpdir):
                    with mock.patch.object(modules.operators, "_now_timestamp", return_value="fallback"):
                        assert "suzanne_va_recordings" in operator._get_recording_path(context)

    modules.operators.SUZANNEVA_OT_microphone_press.recording_path = "out.wav"
    assert operator._recording_output_args()[-1] == "out.wav"

    class FakeProc:
        def __init__(self, poll_value, communicate_result=(b"", b""), communicate_error=None):
            self.poll_value = poll_value
            self.communicate_result = communicate_result
            self.communicate_error = communicate_error

        def poll(self):
            return self.poll_value

        def communicate(self, timeout):
            if self.communicate_error:
                raise self.communicate_error
            return self.communicate_result

    success_proc = FakeProc(None)
    with mock.patch.object(modules.operators, "Popen", return_value=success_proc):
        with mock.patch.object(modules.operators.time, "sleep"):
            success, message = operator._start_process_with_candidates([["ffmpeg"]])
    assert success is True
    assert message == ""
    assert modules.operators.SUZANNEVA_OT_microphone_press.recording_process is success_proc

    fail_proc_one = FakeProc(1, communicate_result=(b"", b"first failure\n"))
    fail_proc_two = FakeProc(1, communicate_error=RuntimeError("boom"))
    with mock.patch.object(modules.operators, "Popen", side_effect=[fail_proc_one, fail_proc_two]):
        with mock.patch.object(modules.operators.time, "sleep"):
            success, message = operator._start_process_with_candidates([["one"], ["two"]])
    assert success is False
    assert message == "recorder process exited immediately."

    modules.operators.SUZANNEVA_OT_microphone_press.recording_process = SimpleNamespace(
        terminate=mock.Mock(),
        wait=mock.Mock(side_effect=modules.operators.TimeoutExpired(cmd="cmd", timeout=3)),
        kill=mock.Mock(),
    )
    operator._stop_recording()
    assert modules.operators.SUZANNEVA_OT_microphone_press.recording_process is None

    with mock.patch.object(modules.operators.time, "time", side_effect=[0, 0]):
        with mock.patch.object(modules.operators.os.path, "exists", return_value=True):
            assert operator._wait_for_file("file.wav") is True

    with mock.patch.object(modules.operators.time, "time", side_effect=[0, 1]):
        assert operator._wait_for_file("missing.wav", timeout_s=0.1) is False


def test_microphone_start_recording_covers_platform_and_error_branches():
    modules = load_suzanne_modules()
    prefs = make_preferences(audio_input_device="custom-device")
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)
    operator = modules.operators.SUZANNEVA_OT_microphone_press()

    with mock.patch.object(modules.operators.platform, "system", return_value="Windows"):
        with mock.patch.object(operator, "_get_recording_path", return_value="record.wav"):
            with mock.patch.object(operator, "_ffmpeg_path", return_value=None):
                assert operator._start_recording(context) is False
    assert "ffmpeg unavailable" in operator._reports[-1][1]

    operator = modules.operators.SUZANNEVA_OT_microphone_press()
    with mock.patch.object(modules.operators.platform, "system", return_value="Darwin"):
        with mock.patch.object(operator, "_get_recording_path", return_value="record.wav"):
            with mock.patch.object(operator, "_atunc_path", return_value=None):
                assert operator._start_recording(context) is False
    assert "atunc not found" in operator._reports[-1][1]

    operator = modules.operators.SUZANNEVA_OT_microphone_press()
    with mock.patch.object(modules.operators.platform, "system", return_value="Windows"):
        with mock.patch.object(operator, "_get_recording_path", return_value="record.wav"):
            with mock.patch.object(operator, "_ffmpeg_path", return_value="ffmpeg"):
                with mock.patch.object(
                    modules.operators,
                    "_get_audio_devices_windows",
                    return_value=[("default", "default", "default"), ("USB Mic", "USB Mic", "USB Mic")],
                ):
                    with mock.patch.object(operator, "_start_process_with_candidates", return_value=(False, "boom")) as start_proc:
                        assert operator._start_recording(context) is False
    built_candidates = start_proc.call_args.args[0]
    assert any("audio=USB Mic" in part for args in built_candidates for part in args)
    assert prefs.audio_input_device == modules.operators._SYSTEM_AUDIO_DEVICE_ID
    assert "Could not start recording: boom" in operator._reports[-1][1]

    operator = modules.operators.SUZANNEVA_OT_microphone_press()
    with mock.patch.object(modules.operators.platform, "system", return_value="Plan9"):
        with mock.patch.object(operator, "_get_recording_path", return_value="record.wav"):
            with mock.patch.object(operator, "_ffmpeg_path", return_value="ffmpeg"):
                with mock.patch.object(operator, "_start_process_with_candidates", return_value=(False, "")):
                    assert operator._start_recording(context) is False
    assert "Could not start recording with system default microphone." in operator._reports[-1][1]


def test_microphone_send_to_chatgpt_covers_failure_and_success_paths():
    modules = load_suzanne_modules()
    operator = modules.operators.SUZANNEVA_OT_microphone_press()

    missing_key_context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(api_key=""))
    ok, message = operator._send_to_chatgpt(missing_key_context, "anything.wav")
    assert ok is False
    assert "Missing OpenAI API key" in message

    file_context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(api_key="sk-live"))
    ok, message = operator._send_to_chatgpt(file_context, "does-not-exist.wav")
    assert ok is False
    assert "Recording file not found" in message

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        audio_path = handle.name
    try:
        with mock.patch.object(
            modules.operators,
            "_transcribe_audio",
            side_effect=modules.operators.URLError("offline"),
        ):
            ok, message = operator._send_to_chatgpt(file_context, audio_path)
        assert ok is False
        assert "Transcription failed" in message

        with mock.patch.object(modules.operators, "_transcribe_audio", return_value={"text": ""}):
            ok, message = operator._send_to_chatgpt(file_context, audio_path)
        assert ok is False
        assert message == "Transcription returned no text."

        file_context.scene.suzanne_va_include_info_history = True
        with mock.patch.object(modules.operators, "_transcribe_audio", return_value={"text": "Hello"}):
            with mock.patch.object(modules.operators, "_get_info_history_lines", return_value=""):
                with mock.patch.object(modules.operators, "_conversation_context_block", return_value="CONTEXT"):
                    with mock.patch.object(modules.operators, "_build_markdown_input", return_value="BUILT"):
                        with mock.patch.object(modules.operators, "_blender_only_prefix", side_effect=lambda text: text):
                            with mock.patch.object(
                                modules.operators,
                                "_call_chatgpt",
                                side_effect=modules.operators.URLError("down"),
                            ):
                                ok, message = operator._send_to_chatgpt(file_context, audio_path)
        assert ok is False
        assert "ChatGPT request failed" in message

        with mock.patch.object(modules.operators, "_transcribe_audio", return_value={"text": "Hello"}):
            with mock.patch.object(modules.operators, "_get_info_history_lines", return_value=""):
                with mock.patch.object(modules.operators, "_conversation_context_block", return_value="CONTEXT"):
                    with mock.patch.object(modules.operators, "_build_markdown_input", return_value="BUILT"):
                        with mock.patch.object(modules.operators, "_blender_only_prefix", side_effect=lambda text: text):
                            with mock.patch.object(
                                modules.operators,
                                "_call_chatgpt",
                                return_value={
                                    "output": [
                                        {
                                            "type": "message",
                                            "content": [
                                                {"type": "output_text", "text": "Hi "},
                                                {"type": "output_text", "text": "there"},
                                            ],
                                        }
                                    ]
                                },
                            ):
                                with mock.patch.object(modules.operators, "_append_conversation_exchange") as append_exchange:
                                    ok, message = operator._send_to_chatgpt(file_context, audio_path)
        assert ok is True
        assert message == ""
        assert file_context.scene.suzanne_va_last_info_history == "(No Info history was captured.)"
        assert file_context.scene.suzanne_va_last_audio == audio_path
        assert file_context.scene.suzanne_va_last_transcript == "Hello"
        assert file_context.scene.suzanne_va_last_response == "Hi there"
        append_exchange.assert_called_once_with(file_context.scene, "Hello", "Hi there", source="voice")
    finally:
        if pathlib.Path(audio_path).exists():
            pathlib.Path(audio_path).unlink()


def test_send_message_and_api_key_cover_more_error_and_fallback_branches():
    modules = load_suzanne_modules()

    no_key_scene = make_scene(suzanne_va_prompt="Hello")
    no_key_context = make_context(modules.common.ADDON_MODULE, scene=no_key_scene, prefs=make_preferences(api_key=""))
    operator = modules.operators.SUZANNEVA_OT_send_message()
    assert operator.execute(no_key_context) == {"CANCELLED"}
    assert "Missing OpenAI API key" in operator._reports[-1][1]

    scene = make_scene(suzanne_va_prompt="Hello", suzanne_va_include_info_history=False)
    context = make_context(modules.common.ADDON_MODULE, scene=scene, prefs=make_preferences(api_key="sk-live"))
    operator = modules.operators.SUZANNEVA_OT_send_message()
    with mock.patch.object(modules.operators, "_conversation_context_block", return_value=""):
        with mock.patch.object(modules.operators, "_build_markdown_input", return_value="BUILT"):
            with mock.patch.object(modules.operators, "_blender_only_prefix", return_value="PREFIX"):
                with mock.patch.object(
                    modules.operators,
                    "_call_chatgpt",
                    return_value={
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": "Chunked reply"}],
                            }
                        ]
                    },
                ):
                    with mock.patch.object(modules.operators, "_append_conversation_exchange"):
                        with mock.patch.object(modules.operators, "_tag_redraw_all"):
                            assert operator.execute(context) == {"FINISHED"}
    assert scene.suzanne_va_last_info_history == ""
    assert scene.suzanne_va_last_response == "Chunked reply"

    api_operator = modules.operators.SUZANNEVA_OT_test_api_key()
    api_context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(api_key="sk-live"))

    http_error = modules.operators.HTTPError("https://api.openai.com/v1/models", 401, "bad", None, None)
    with mock.patch.object(modules.operators, "_get_json", side_effect=http_error):
        with mock.patch.object(modules.operators, "_read_http_error_body", return_value="denied"):
            with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
                assert api_operator.execute(api_context) == {"CANCELLED"}
    assert "HTTP 401 | denied" in set_diag.call_args.kwargs["error"]

    with mock.patch.object(modules.operators, "_get_json", side_effect=modules.operators.URLError("offline")):
        with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
            assert api_operator.execute(api_context) == {"CANCELLED"}
    assert "API key test failed" in set_diag.call_args.kwargs["error"]

    with mock.patch.object(modules.operators, "_get_json", return_value="not-json"):
        with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
            assert api_operator.execute(api_context) == {"CANCELLED"}
    assert set_diag.call_args.kwargs["error"] == "API key test failed: invalid JSON response"


def test_misc_operator_error_paths_cover_copy_transcription_and_conversation_failures():
    modules = load_suzanne_modules()

    copy_context = make_context(
        modules.common.ADDON_MODULE,
        prefs=make_preferences(diagnostics_last_error=""),
    )
    copy_operator = modules.operators.SUZANNEVA_OT_copy_last_error()
    assert copy_operator.execute(copy_context) == {"CANCELLED"}

    test_transcription = modules.operators.SUZANNEVA_OT_test_transcription()
    valid_context = make_context(modules.common.ADDON_MODULE, prefs=make_preferences(api_key="sk-live"))

    with mock.patch.object(modules.operators, "_write_silence_wav"):
        with mock.patch.object(
            modules.operators,
            "_transcribe_audio",
            side_effect=modules.operators.URLError("offline"),
        ):
            with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
                assert test_transcription.execute(valid_context) == {"CANCELLED"}
    assert "Transcription test failed" in set_diag.call_args.kwargs["error"]

    with mock.patch.object(modules.operators, "_write_silence_wav"):
        with mock.patch.object(modules.operators, "_transcribe_audio", return_value="not-a-dict"):
            with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
                assert test_transcription.execute(valid_context) == {"CANCELLED"}
    assert set_diag.call_args.kwargs["error"] == "Transcription test failed: invalid response format."

    with mock.patch.object(modules.operators, "_write_silence_wav"):
        with mock.patch.object(modules.operators, "_transcribe_audio", return_value={"text": ""}):
            with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
                assert test_transcription.execute(valid_context) == {"FINISHED"}
    assert set_diag.call_args.kwargs["message"] == "Transcription test passed. Empty text is expected for silence."

    new_context = make_context(modules.common.ADDON_MODULE, scene=make_scene(suzanne_va_prompt="Hello"))
    new_operator = modules.operators.SUZANNEVA_OT_new_conversation()
    with mock.patch.object(modules.operators, "_new_conversation", return_value=None):
        assert new_operator.execute(new_context) == {"CANCELLED"}

    rename_operator = modules.operators.SUZANNEVA_OT_rename_conversation()
    rename_operator.new_title = "New title"
    rename_operator.layout = SimpleNamespace(prop=mock.Mock())
    rename_operator.draw(None)
    rename_operator.layout.prop.assert_called_once_with(rename_operator, "new_title", text="Title")
    with mock.patch.object(modules.operators, "_rename_conversation", return_value=False):
        assert rename_operator.execute(new_context) == {"CANCELLED"}

    delete_operator = modules.operators.SUZANNEVA_OT_delete_conversation()
    with mock.patch.object(modules.operators, "_delete_active_conversation", return_value=False):
        assert delete_operator.execute(new_context) == {"CANCELLED"}


def test_microphone_press_execute_handles_send_failure_branch():
    modules = load_suzanne_modules()
    scene = make_scene(suzanne_va_mic_active=True)
    context = make_context(modules.common.ADDON_MODULE, scene=scene)
    operator = modules.operators.SUZANNEVA_OT_microphone_press()
    modules.operators.SUZANNEVA_OT_microphone_press.recording_path = "recording.wav"

    with mock.patch.object(operator, "_stop_recording"):
        with mock.patch.object(operator, "_wait_for_file", return_value=True):
            with mock.patch.object(operator, "_send_to_chatgpt", return_value=(False, "upload failed")):
                with mock.patch.object(modules.operators, "_tag_redraw_all") as redraw:
                    assert operator.execute(context) == {"FINISHED"}

    assert scene.suzanne_va_mic_active is False
    assert scene.suzanne_va_status == "Idle (error)"
    assert "upload failed" in operator._reports[-1][1]
    assert redraw.call_count == 2


def test_microphone_start_recording_covers_remaining_success_branches():
    modules = load_suzanne_modules()
    prefs = make_preferences(audio_input_device="custom-device")
    context = make_context(modules.common.ADDON_MODULE, prefs=prefs)

    linux_operator = modules.operators.SUZANNEVA_OT_microphone_press()
    with mock.patch.object(modules.operators.platform, "system", return_value="Linux"):
        with mock.patch.object(linux_operator, "_get_recording_path", return_value="record.wav"):
            with mock.patch.object(modules.operators, "_get_addon_preferences", side_effect=RuntimeError("boom")):
                with mock.patch.object(linux_operator, "_ffmpeg_path", return_value="ffmpeg"):
                    with mock.patch.object(
                        linux_operator,
                        "_start_process_with_candidates",
                        return_value=(True, ""),
                    ) as start_proc:
                        assert linux_operator._start_recording(context) is True

    linux_candidates = start_proc.call_args.args[0]
    assert linux_candidates[0][:4] == ["ffmpeg", "-f", "alsa", "-i"]
    assert linux_candidates[1][:4] == ["ffmpeg", "-f", "pulse", "-i"]

    darwin_operator = modules.operators.SUZANNEVA_OT_microphone_press()
    with mock.patch.object(modules.operators.platform, "system", return_value="Darwin"):
        with mock.patch.object(darwin_operator, "_get_recording_path", return_value="record.wav"):
            with mock.patch.object(darwin_operator, "_atunc_path", return_value="atunc"):
                with mock.patch.object(
                    modules.operators,
                    "_get_audio_devices_macos",
                    return_value=[("default", "default", "default"), ("7", "Built-in Mic", "Built-in Mic")],
                ):
                    with mock.patch.object(
                        darwin_operator,
                        "_start_process_with_candidates",
                        return_value=(True, ""),
                    ) as start_proc:
                        assert darwin_operator._start_recording(context) is True

    darwin_candidates = start_proc.call_args.args[0]
    assert any(candidate[2] == "7" for candidate in darwin_candidates[1:])
    assert prefs.audio_input_device == modules.operators._SYSTEM_AUDIO_DEVICE_ID


def test_microphone_helpers_cover_wait_loop_and_no_history_voice_send():
    modules = load_suzanne_modules()
    operator = modules.operators.SUZANNEVA_OT_microphone_press()

    modules.operators.SUZANNEVA_OT_microphone_press.recording_process = None
    assert operator._stop_recording() is None

    with mock.patch.object(modules.operators.os.path, "exists", return_value=False):
        with mock.patch.object(modules.operators.time, "time", side_effect=[0, 0, 0.2]):
            with mock.patch.object(modules.operators.time, "sleep") as sleep:
                assert operator._wait_for_file("missing.wav", timeout_s=0.1) is False
    sleep.assert_called_once_with(0.1)

    context = make_context(
        modules.common.ADDON_MODULE,
        prefs=make_preferences(api_key="sk-live"),
    )
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        audio_path = handle.name
    try:
        with mock.patch.object(modules.operators, "_transcribe_audio", return_value={"text": "Hello"}):
            with mock.patch.object(modules.operators, "_conversation_context_block", return_value=""):
                with mock.patch.object(modules.operators, "_build_markdown_input", return_value="BUILT"):
                    with mock.patch.object(modules.operators, "_blender_only_prefix", side_effect=lambda text: text):
                        with mock.patch.object(
                            modules.operators,
                            "_call_chatgpt",
                            return_value={"output_text": "Hi"},
                        ):
                            with mock.patch.object(
                                modules.operators,
                                "_append_conversation_exchange",
                            ) as append_exchange:
                                ok, message = operator._send_to_chatgpt(context, audio_path)

        assert ok is True
        assert message == ""
        assert context.scene.suzanne_va_last_info_history == ""
        append_exchange.assert_called_once_with(context.scene, "Hello", "Hi", source="voice")
    finally:
        audio_file = pathlib.Path(audio_path)
        if audio_file.exists():
            audio_file.unlink()


def test_test_transcription_execute_covers_generic_exception_and_cleanup_failure():
    modules = load_suzanne_modules()
    context = make_context(
        modules.common.ADDON_MODULE,
        prefs=make_preferences(api_key="sk-live"),
    )
    operator = modules.operators.SUZANNEVA_OT_test_transcription()
    removed_path = {}

    def failing_remove(path):
        removed_path["value"] = path
        raise OSError("locked")

    with mock.patch.object(modules.operators, "_write_silence_wav"):
        with mock.patch.object(modules.operators, "_transcribe_audio", side_effect=RuntimeError("boom")):
            with mock.patch.object(modules.operators.os.path, "exists", return_value=True):
                with mock.patch.object(modules.operators.os, "remove", side_effect=failing_remove):
                    with mock.patch.object(modules.operators, "_set_diagnostics_message") as set_diag:
                        assert operator.execute(context) == {"CANCELLED"}

    assert set_diag.call_args.kwargs["error"] == "Transcription test failed: boom"

    temp_file = pathlib.Path(removed_path["value"])
    if temp_file.exists():
        temp_file.unlink()
