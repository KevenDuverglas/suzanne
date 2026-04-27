import pathlib
from unittest import mock

from tests.test_support import LayoutRecorder, load_suzanne_modules


def test_preferences_draw_masks_api_key_and_renders_diagnostics_controls():
    modules = load_suzanne_modules()
    prefs = modules.preferences.SUZANNEVA_Preferences()
    prefs.api_key = "sk-1234567890"
    prefs.show_api_key = False
    prefs.diagnostics_last_message = "Models refreshed."
    prefs.diagnostics_last_error = "Network issue."
    prefs.layout = LayoutRecorder()

    with mock.patch.object(modules.preferences, "_os_display_name", return_value="Windows"):
        with mock.patch.object(
            modules.preferences,
            "_recordings_dir",
            return_value=pathlib.Path("C:/temp/recordings"),
        ):
            with mock.patch.object(
                modules.preferences,
                "_wrap_ui_text",
                side_effect=lambda text, width: [str(text)],
            ):
                prefs.draw(None)

    labels = prefs.layout.label_texts()
    operator_ids = prefs.layout.operator_ids()

    assert "Suzanne Version 1.0.0" in labels
    assert any(label.startswith("API Key: ") for label in labels)
    assert "Last Result" in labels
    assert "Last Error" in labels
    assert "suzanne_va.test_api_key" in operator_ids
    assert "suzanne_va.copy_last_error" in operator_ids


def test_preferences_draw_shows_plain_api_key_when_reveal_is_enabled():
    modules = load_suzanne_modules()
    prefs = modules.preferences.SUZANNEVA_Preferences()
    prefs.api_key = "sk-live"
    prefs.show_api_key = True
    prefs.diagnostics_last_message = ""
    prefs.diagnostics_last_error = ""
    prefs.layout = LayoutRecorder()

    with mock.patch.object(modules.preferences, "_os_display_name", return_value="Windows"):
        with mock.patch.object(
            modules.preferences,
            "_recordings_dir",
            return_value=pathlib.Path("C:/temp/recordings"),
        ):
            with mock.patch.object(
                modules.preferences,
                "_wrap_ui_text",
                side_effect=lambda text, width: [str(text)],
            ):
                prefs.draw(None)

    api_row = prefs.layout.children[0]
    assert ("prop", (prefs, "api_key"), {"text": "API Key"}) in api_row.calls
    assert ("prop", (prefs, "show_api_key"), {"text": "Hide"}) in api_row.calls
    assert not any(label.startswith("API Key: ") for label in prefs.layout.label_texts())
