from .common import *  # noqa: F403,F401
from .operators import (  # noqa: F401
    SUZANNEVA_OT_send_message,
    SUZANNEVA_OT_microphone_press,
    SUZANNEVA_OT_new_conversation,
    SUZANNEVA_OT_rename_conversation,
    SUZANNEVA_OT_delete_conversation,
)

# ----------------------------- panel ---------------------------

class SUZANNEVA_PT_sidebar(Panel):
    bl_label = "Suzanne Voice Assistant"
    bl_idname = "SUZANNEVA_PT_sidebar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Suzanne"

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def draw_header(self, context):
        layout = self.layout
        is_on = context.scene.suzanne_va_mic_active
        layout.label(icon='REC' if is_on else 'MUTE_IPO_OFF')

    def _draw_status_card(self, layout, scene, is_recording):
        status_text, status_icon, status_alert = _status_visual(scene.suzanne_va_status, is_recording)
        status_box = layout.box()
        status_row = status_box.row(align=True)
        status_row.alert = status_alert
        status_row.scale_y = 1.05
        status_row.label(text=f" {status_text}", icon=status_icon)
        layout.separator()

    def _draw_ask_card(self, layout, scene):
        ask_box = layout.box()
        if _draw_section_header(
            ask_box,
            scene,
            "suzanne_va_show_message",
            "Ask",
            'OUTLINER_OB_SPEAKER',
        ):
            ask_col = ask_box.column(align=True)
            ask_col.prop(scene, "suzanne_va_prompt", text="")
            send_row = ask_col.row(align=True)
            send_row.scale_y = 1.05
            send_row.operator(SUZANNEVA_OT_send_message.bl_idname, icon='FORWARD')
        layout.separator()

    def _draw_context_card(self, layout, scene):
        context_box = layout.box()
        if _draw_section_header(
            context_box,
            scene,
            "suzanne_va_show_context",
            "Context",
            'PREFERENCES',
        ):
            context_col = context_box.column(align=True)
            context_col.prop(scene, "suzanne_va_use_conversation_context", text="Use Conversation Context")
            if scene.suzanne_va_use_conversation_context:
                context_col.prop(scene, "suzanne_va_context_turns", text="Context Turns")
            context_col.prop(scene, "suzanne_va_include_info_history", text="Include Info History (100 lines)")
        layout.separator()

    def _draw_conversation_card(self, layout, scene):
        conversation_box = layout.box()
        if _draw_section_header(
            conversation_box,
            scene,
            "suzanne_va_show_conversation",
            "Conversation",
            'TEXT',
        ):
            conversation_col = conversation_box.column(align=True)
            controls_row = conversation_col.row(align=True)
            controls_row.prop(scene, "suzanne_va_active_conversation", text="")
            controls_row.operator(SUZANNEVA_OT_new_conversation.bl_idname, text="", icon='ADD')

            active_conversation_id = str(scene.suzanne_va_active_conversation or "").strip()
            has_conversation = bool(active_conversation_id) and active_conversation_id != _NO_CONVERSATION_ID

            rename_row = controls_row.row(align=True)
            rename_row.enabled = has_conversation
            rename_row.operator(SUZANNEVA_OT_rename_conversation.bl_idname, text="", icon='GREASEPENCIL')

            delete_row = controls_row.row(align=True)
            delete_row.enabled = has_conversation
            delete_row.operator(SUZANNEVA_OT_delete_conversation.bl_idname, text="", icon='TRASH')

            conversation_col.separator()
            preview_lines = _conversation_preview_lines(
                scene,
                max_items=max(2, min(14, scene.suzanne_va_context_turns * 2)),
            )
            if preview_lines:
                for line in preview_lines:
                    conversation_col.label(text=line)
            else:
                conversation_col.label(text="No saved messages yet.", icon='INFO')
        layout.separator()

    def _draw_voice_card(self, layout, scene, is_recording):
        voice_box = layout.box()
        if _draw_section_header(
            voice_box,
            scene,
            "suzanne_va_show_recording",
            "Voice",
            'REC',
        ):
            voice_col = voice_box.column(align=True)
            record_row = voice_col.row(align=True)
            record_row.alert = is_recording
            record_text = "Stop Recording" if is_recording else "Microphone"
            record_icon = 'REC' if is_recording else 'MUTE_IPO_OFF'
            record_row.operator(
                SUZANNEVA_OT_microphone_press.bl_idname,
                text=record_text,
                icon=record_icon,
            )
        layout.separator()

    def _draw_latest_output_card(self, layout, scene):
        has_transcript = bool((scene.suzanne_va_last_transcript or "").strip())
        has_response = bool((scene.suzanne_va_last_response or "").strip())
        if not has_transcript and not has_response:
            return

        output_box = layout.box()
        if not _draw_section_header(
            output_box,
            scene,
            "suzanne_va_show_output",
            "Latest Output",
            'CHECKMARK',
        ):
            return

        output_col = output_box.column(align=True)
        if has_transcript and has_response:
            output_col.prop(scene, "suzanne_va_output_view", expand=True)

        selected_view = scene.suzanne_va_output_view
        if selected_view == "transcript" and not has_transcript:
            selected_view = "response"
        if selected_view == "response" and not has_response:
            selected_view = "transcript"

        if selected_view == "transcript":
            output_col.label(text="Transcript", icon='TEXT')
            transcript_lines, transcript_needs_toggle = _preview_response_lines(
                scene.suzanne_va_last_transcript,
                width=80,
                max_lines=_TRANSCRIPT_PREVIEW_LINES,
                expanded=scene.suzanne_va_expand_transcript,
            )
            for line in transcript_lines:
                output_col.label(text=line)
            if transcript_needs_toggle:
                _draw_expand_toggle(output_col, scene, "suzanne_va_expand_transcript")
            return

        output_col.label(text="ChatGPT Response", icon='CHECKMARK')
        response_lines, response_needs_toggle = _preview_response_lines(
            scene.suzanne_va_last_response,
            width=80,
            max_lines=_RESPONSE_PREVIEW_LINES,
            expanded=scene.suzanne_va_expand_response,
        )
        for line in response_lines:
            if line.lower().startswith("step "):
                output_col.label(text=line, icon='CHECKMARK')
            else:
                output_col.label(text=line)
        if response_needs_toggle:
            _draw_expand_toggle(output_col, scene, "suzanne_va_expand_response")

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        is_recording = scene.suzanne_va_mic_active

        self._draw_status_card(layout, scene, is_recording)
        self._draw_ask_card(layout, scene)
        self._draw_voice_card(layout, scene, is_recording)
        self._draw_context_card(layout, scene)
        self._draw_conversation_card(layout, scene)
        self._draw_latest_output_card(layout, scene)
