from .common import *  # noqa: F403,F401

# ------------------------ preferences --------------------------

class SUZANNEVA_Preferences(AddonPreferences):
    bl_idname = ADDON_MODULE

    api_key: StringProperty(
        name="OpenAI API Key",
        description="API key used to send recordings to ChatGPT",
        default="",
    )
    show_api_key: BoolProperty(
        name="Show API Key",
        description="Reveal or hide the API key",
        default=False,
    )
    response_model: EnumProperty(
        name="ChatGPT Model",
        description="Model for the response (Responses API)",
        items=_model_enum_items,
    )
    transcription_model: EnumProperty(
        name="Transcription Model",
        description="Model used for audio transcription",
        items=_transcribe_model_enum_items,
    )
    audio_input_device: EnumProperty(
        name="Audio Input Device",
        description="Single system-default microphone option with OS-specific fallback handling",
        items=_audio_devices_enum_items,
    )
    file_prefix: StringProperty(
        name="File Prefix",
        description="Prefix for recorded file names",
        default="suzanne_va_",
    )
    auto_save_conversations: BoolProperty(
        name="Auto-save Conversations",
        description="Automatically append each user/assistant exchange to local conversation history",
        default=True,
    )
    diagnostics_last_message: StringProperty(
        name="Diagnostics Message",
        default="",
    )
    diagnostics_last_error: StringProperty(
        name="Last Error",
        default="",
    )

    def draw(self, _context):
        layout = self.layout
        os_name = _os_display_name()
        layout.label(text=f"Recording Settings ({os_name})")
        layout.label(text=f"Microphone: System Default ({os_name})")
        layout.prop(self, "file_prefix")
        layout.separator()

        layout.label(text="OpenAI Settings")
        row = layout.row(align=True)
        if self.show_api_key:
            row.prop(self, "api_key", text="API Key")
            row.prop(self, "show_api_key", text="Hide")
        else:
            masked = "*" * max(8, min(32, len(self.api_key)))
            row.label(text=f"API Key: {masked}")
            row.prop(self, "show_api_key", text="Show")
        row.operator("suzanne_va.clear_saved_api_key", text="Clear")

        row = layout.row(align=True)
        row.prop(self, "response_model")
        row.operator("suzanne_va.refresh_models", text="Refresh")

        row = layout.row(align=True)
        row.prop(self, "transcription_model")
        row.operator("suzanne_va.refresh_models", text="Refresh")

        layout.separator()
        layout.label(text="Conversation Storage")
        layout.prop(self, "auto_save_conversations")

        recordings_path = str(_recordings_dir())
        recordings_box = layout.box()
        recordings_box.label(text="Recordings Folder")
        for line in _wrap_ui_text(recordings_path, width=78):
            recordings_box.label(text=line)
        recordings_box.operator("suzanne_va.open_recordings_folder", text="Open Recordings Folder")

        layout.separator()
        layout.label(text="Diagnostics")
        diag_row = layout.row(align=True)
        diag_row.operator("suzanne_va.test_api_key", text="Test API Key")
        diag_row.operator("suzanne_va.test_microphone", text="Test Microphone")
        diag_row.operator("suzanne_va.test_transcription", text="Test Transcription")

        if self.diagnostics_last_message:
            info_box = layout.box()
            info_box.label(text="Last Result")
            for line in _wrap_ui_text(self.diagnostics_last_message, width=78):
                info_box.label(text=line)

        if self.diagnostics_last_error:
            error_box = layout.box()
            header = error_box.row(align=True)
            header.alert = True
            header.label(text="Last Error")
            header.operator("suzanne_va.copy_last_error", text="Copy")
            for line in _wrap_ui_text(self.diagnostics_last_error, width=78):
                error_box.label(text=line)
