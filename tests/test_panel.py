from types import SimpleNamespace
from unittest import mock

from tests.test_support import FakeCollection, LayoutRecorder, load_suzanne_modules, make_context, make_scene


def test_panel_status_presentation_maps_common_states():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()
    scene = make_scene(suzanne_va_status="Idle")

    assert sidebar._status_presentation(scene, False) == (
        "Ready",
        "Ask a Blender question or record audio to begin.",
        "INFO",
        False,
    )

    scene.suzanne_va_status = "Idle (error)"
    assert sidebar._status_presentation(scene, False) == (
        "Error",
        "Idle (error)",
        "ERROR",
        True,
    )

    scene.suzanne_va_status = "Sending..."
    assert sidebar._status_presentation(scene, False)[0] == "Sending..."

    scene.suzanne_va_status = "Stopping..."
    assert sidebar._status_presentation(scene, False)[0] == "Finishing recording..."

    scene.suzanne_va_status = "Idle (sent)"
    assert sidebar._status_presentation(scene, False)[2] == "CHECKMARK"

    assert sidebar._status_presentation(scene, True)[0] == "Recording..."


def test_panel_draw_delegates_to_all_section_renderers():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()
    scene = make_scene(suzanne_va_mic_active=False)
    context = make_context(modules.common.ADDON_MODULE, scene=scene)
    sidebar.layout = LayoutRecorder()

    with mock.patch.object(sidebar, "_draw_status_card") as draw_status:
        with mock.patch.object(sidebar, "_draw_ask_card") as draw_ask:
            with mock.patch.object(sidebar, "_draw_voice_card") as draw_voice:
                with mock.patch.object(sidebar, "_draw_context_card") as draw_context:
                    with mock.patch.object(sidebar, "_draw_conversation_card") as draw_conversation:
                        with mock.patch.object(sidebar, "_draw_latest_output_card") as draw_latest:
                            sidebar.draw(context)

    draw_status.assert_called_once_with(sidebar.layout, scene, False)
    draw_ask.assert_called_once_with(sidebar.layout, scene)
    draw_voice.assert_called_once_with(sidebar.layout, scene, False)
    draw_context.assert_called_once_with(sidebar.layout, scene)
    draw_conversation.assert_called_once_with(sidebar.layout, scene)
    draw_latest.assert_called_once_with(sidebar.layout, scene)


def test_panel_sync_conversation_preview_uses_placeholder_when_no_conversation_exists():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()
    preview_items = FakeCollection()
    scene = make_scene(
        suzanne_va_conversation_preview=preview_items,
        suzanne_va_conversation_preview_index=5,
        suzanne_va_active_conversation="",
    )

    with mock.patch.object(modules.panel, "_conversation_preview_lines", return_value=[]):
        sidebar._sync_conversation_preview(scene)

    assert len(preview_items) == 1
    assert preview_items[0].label == "No conversation yet. Create one or send a prompt."
    assert preview_items[0].is_placeholder is True
    assert scene.suzanne_va_conversation_preview_index == 0


def test_panel_sync_conversation_preview_reuses_real_preview_lines_and_trims_rows():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()
    preview_items = FakeCollection(
        [
            SimpleNamespace(label="old 1", is_placeholder=True),
            SimpleNamespace(label="old 2", is_placeholder=True),
            SimpleNamespace(label="old 3", is_placeholder=True),
        ]
    )
    scene = make_scene(
        suzanne_va_conversation_preview=preview_items,
        suzanne_va_active_conversation="conv-1",
    )

    with mock.patch.object(
        modules.panel,
        "_conversation_preview_lines",
        return_value=["You: Hi", "Suzanne: Hello"],
    ):
        sidebar._sync_conversation_preview(scene)

    assert len(preview_items) == 2
    assert preview_items[0].label == "You: Hi"
    assert preview_items[0].is_placeholder is False
    assert preview_items[1].label == "Suzanne: Hello"
    assert preview_items[1].is_placeholder is False


def test_panel_preview_list_poll_and_header_cover_basic_ui_branches():
    modules = load_suzanne_modules()
    preview = modules.panel.SUZANNEVA_UL_conversation_preview()

    grid_layout = LayoutRecorder()
    preview.layout_type = "GRID"
    preview.draw_item(
        None,
        grid_layout,
        None,
        SimpleNamespace(label="Ignored", is_placeholder=False),
        None,
        None,
        None,
    )
    assert grid_layout.alignment == "CENTER"
    assert grid_layout.calls[0][1]["text"] == ""

    placeholder_layout = LayoutRecorder()
    preview.layout_type = "DEFAULT"
    preview.draw_item(
        None,
        placeholder_layout,
        None,
        SimpleNamespace(label="Placeholder", is_placeholder=True),
        None,
        None,
        None,
    )
    placeholder_row = placeholder_layout.children[0]
    assert placeholder_row.enabled is False
    assert "Placeholder" in placeholder_layout.label_texts()

    normal_layout = LayoutRecorder()
    preview.draw_item(
        None,
        normal_layout,
        None,
        SimpleNamespace(label="Normal", is_placeholder=False),
        None,
        None,
        None,
    )
    assert "Normal" in normal_layout.label_texts()

    sidebar = modules.panel.SUZANNEVA_PT_sidebar()
    view_context = make_context(modules.common.ADDON_MODULE, scene=make_scene(suzanne_va_mic_active=True))
    non_view_context = make_context(modules.common.ADDON_MODULE)
    non_view_context.area.type = "IMAGE_EDITOR"
    assert modules.panel.SUZANNEVA_PT_sidebar.poll(view_context) is True
    assert modules.panel.SUZANNEVA_PT_sidebar.poll(non_view_context) is False

    sidebar.layout = LayoutRecorder()
    sidebar.draw_header(view_context)
    assert sidebar.layout.calls[0][1]["icon"] == "REC"


def test_panel_draw_cards_render_controls_and_empty_states():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()
    scene = make_scene()

    with mock.patch.object(modules.panel, "_wrap_ui_text", return_value=["Status detail"]):
        status_layout = LayoutRecorder()
        sidebar._draw_status_card(status_layout, scene, False)
    assert "Ready" in status_layout.label_texts()
    assert "Status detail" in status_layout.label_texts()

    ask_layout = LayoutRecorder()
    sidebar._draw_ask_card(ask_layout, scene)
    assert "Ask a Blender question to start." in ask_layout.label_texts()
    assert modules.operators.SUZANNEVA_OT_send_message.bl_idname in ask_layout.operator_ids()

    context_layout = LayoutRecorder()
    sidebar._draw_context_card(context_layout, scene)
    assert "Context" in context_layout.label_texts()

    conversation_layout = LayoutRecorder()
    with mock.patch.object(sidebar, "_sync_conversation_preview") as sync_preview:
        sidebar._draw_conversation_card(conversation_layout, scene)
    sync_preview.assert_called_once_with(scene)
    assert modules.operators.SUZANNEVA_OT_new_conversation.bl_idname in conversation_layout.operator_ids()
    assert modules.operators.SUZANNEVA_OT_rename_conversation.bl_idname in conversation_layout.operator_ids()
    assert modules.operators.SUZANNEVA_OT_delete_conversation.bl_idname in conversation_layout.operator_ids()

    voice_layout = LayoutRecorder()
    sidebar._draw_voice_card(voice_layout, scene, False)
    assert "Record a quick prompt and Suzanne will send it." in voice_layout.label_texts()
    assert modules.operators.SUZANNEVA_OT_microphone_press.bl_idname in voice_layout.operator_ids()

    empty_output_layout = LayoutRecorder()
    sidebar._draw_latest_output_card(empty_output_layout, scene)
    assert "No response yet. Send a prompt or record audio." in empty_output_layout.label_texts()


def test_panel_draw_latest_output_card_handles_transcript_and_response_views():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()

    transcript_scene = make_scene(
        suzanne_va_last_transcript="Transcript text",
        suzanne_va_last_response="",
        suzanne_va_output_view="response",
    )
    transcript_layout = LayoutRecorder()
    with mock.patch.object(
        modules.panel,
        "_preview_response_lines",
        return_value=(["Transcript line"], True),
    ):
        with mock.patch.object(modules.panel, "_draw_expand_toggle") as draw_toggle:
            sidebar._draw_latest_output_card(transcript_layout, transcript_scene)
    assert "Transcript" in transcript_layout.label_texts()
    draw_toggle.assert_called_once_with(mock.ANY, transcript_scene, "suzanne_va_expand_transcript")

    response_scene = make_scene(
        suzanne_va_last_transcript="Prompt text",
        suzanne_va_last_response="Step 1\nDone",
        suzanne_va_output_view="response",
    )
    response_layout = LayoutRecorder()
    with mock.patch.object(
        modules.panel,
        "_preview_response_lines",
        return_value=(["Step 1", "Done"], True),
    ):
        with mock.patch.object(modules.panel, "_draw_expand_toggle") as draw_toggle:
            sidebar._draw_latest_output_card(response_layout, response_scene)
    assert "ChatGPT Response" in response_layout.label_texts()
    draw_toggle.assert_called_once_with(mock.ANY, response_scene, "suzanne_va_expand_response")


def test_panel_covers_collapsed_cards_and_remaining_status_fallbacks():
    modules = load_suzanne_modules()
    sidebar = modules.panel.SUZANNEVA_PT_sidebar()

    scene = make_scene(suzanne_va_status="Custom ready")
    assert sidebar._status_presentation(scene, False) == (
        "Ready",
        "Custom ready",
        "INFO",
        False,
    )

    preview_items = FakeCollection()
    preview_scene = make_scene(
        suzanne_va_conversation_preview=preview_items,
        suzanne_va_active_conversation="conv-1",
    )
    with mock.patch.object(modules.panel, "_conversation_preview_lines", return_value=[]):
        sidebar._sync_conversation_preview(preview_scene)
    assert preview_items[0].label == "No saved messages yet. Start by asking a question."

    ask_layout = LayoutRecorder(collapsed_props={"suzanne_va_show_message"})
    sidebar._draw_ask_card(ask_layout, make_scene())
    assert any(call[0] == "separator" for call in ask_layout.calls)

    context_layout = LayoutRecorder(collapsed_props={"suzanne_va_show_context"})
    sidebar._draw_context_card(context_layout, make_scene())
    assert any(call[0] == "separator" for call in context_layout.calls)

    conversation_layout = LayoutRecorder(collapsed_props={"suzanne_va_show_conversation"})
    sidebar._draw_conversation_card(conversation_layout, make_scene())
    assert any(call[0] == "separator" for call in conversation_layout.calls)

    voice_layout = LayoutRecorder(collapsed_props={"suzanne_va_show_recording"})
    sidebar._draw_voice_card(voice_layout, make_scene(), False)
    assert any(call[0] == "separator" for call in voice_layout.calls)

    output_layout = LayoutRecorder(collapsed_props={"suzanne_va_show_output"})
    sidebar._draw_latest_output_card(output_layout, make_scene())
    assert output_layout.label_texts() == ["Latest Output"]

    switched_scene = make_scene(
        suzanne_va_last_transcript="",
        suzanne_va_last_response="Only response",
        suzanne_va_output_view="transcript",
    )
    switched_layout = LayoutRecorder()
    with mock.patch.object(
        modules.panel,
        "_preview_response_lines",
        return_value=(["Only response"], False),
    ):
        sidebar._draw_latest_output_card(switched_layout, switched_scene)
    assert "ChatGPT Response" in switched_layout.label_texts()
