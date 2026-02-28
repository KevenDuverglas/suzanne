from bpy.props import CollectionProperty
from bpy.types import PropertyGroup

from .common import *  # noqa: F403,F401

# --------------------------- state -----------------------------
# Use Scene properties (reliable & per-file). No WindowManager quirks.

_SCENE_PROP_NAMES = (
    "suzanne_va_mic_active",
    "suzanne_va_status",
    "suzanne_va_last_audio",
    "suzanne_va_last_transcript",
    "suzanne_va_last_response",
    "suzanne_va_prompt",
    "suzanne_va_active_conversation",
    "suzanne_va_use_conversation_context",
    "suzanne_va_context_turns",
    "suzanne_va_include_info_history",
    "suzanne_va_last_info_history",
    "suzanne_va_show_message",
    "suzanne_va_show_context",
    "suzanne_va_show_conversation",
    "suzanne_va_show_recording",
    "suzanne_va_show_output",
    "suzanne_va_output_view",
    "suzanne_va_expand_transcript",
    "suzanne_va_expand_response",
    "suzanne_va_conversation_preview",
    "suzanne_va_conversation_preview_index",
)


class SUZANNEVA_PG_conversation_preview_item(PropertyGroup):
    label: StringProperty(
        name="Conversation Preview Line",
        default="",
    )
    is_placeholder: BoolProperty(
        name="Placeholder Row",
        default=False,
    )


def ensure_props():
    sc = bpy.types.Scene
    if not hasattr(sc, "suzanne_va_mic_active"):
        sc.suzanne_va_mic_active = BoolProperty(
            name="Microphone Active",
            description="Internal state for the Microphone button",
            default=False,
        )
    if not hasattr(sc, "suzanne_va_status"):
        sc.suzanne_va_status = StringProperty(
            name="Status",
            description="Display text shown above the button",
            default="Idle",
        )
    if not hasattr(sc, "suzanne_va_last_audio"):
        sc.suzanne_va_last_audio = StringProperty(
            name="Last Audio File",
            description="Most recent recording file path",
            default="",
        )
    if not hasattr(sc, "suzanne_va_last_transcript"):
        sc.suzanne_va_last_transcript = StringProperty(
            name="Last Transcript",
            description="Most recent transcription text",
            default="",
        )
    if not hasattr(sc, "suzanne_va_last_response"):
        sc.suzanne_va_last_response = StringProperty(
            name="Last ChatGPT Response",
            description="Most recent ChatGPT response text",
            default="",
        )
    if not hasattr(sc, "suzanne_va_prompt"):
        sc.suzanne_va_prompt = StringProperty(
            name="Prompt",
            description="Type a message to send to ChatGPT",
            default="",
        )
    if not hasattr(sc, "suzanne_va_active_conversation"):
        sc.suzanne_va_active_conversation = EnumProperty(
            name="Conversation",
            description="Choose a locally saved conversation",
            items=_conversation_enum_items,
        )
    if not hasattr(sc, "suzanne_va_use_conversation_context"):
        sc.suzanne_va_use_conversation_context = BoolProperty(
            name="Use Conversation Context",
            description="Include recent messages from the selected local conversation",
            default=True,
        )
    if not hasattr(sc, "suzanne_va_context_turns"):
        sc.suzanne_va_context_turns = IntProperty(
            name="Context Turns",
            description="How many recent user/assistant turns to include",
            default=4,
            min=1,
            max=20,
        )
    if not hasattr(sc, "suzanne_va_include_info_history"):
        sc.suzanne_va_include_info_history = BoolProperty(
            name="Include Blender Info History",
            description="Send the last 100 lines from Blender Info with text and voice prompts",
            default=False,
        )
    if not hasattr(sc, "suzanne_va_last_info_history"):
        sc.suzanne_va_last_info_history = StringProperty(
            name="Last Attached Info History",
            description="Most recent Blender Info history block sent with a prompt",
            default="",
        )
    if not hasattr(sc, "suzanne_va_show_message"):
        sc.suzanne_va_show_message = BoolProperty(
            name="Show Ask Section",
            default=True,
        )
    if not hasattr(sc, "suzanne_va_show_context"):
        sc.suzanne_va_show_context = BoolProperty(
            name="Show Context Section",
            default=False,
        )
    if not hasattr(sc, "suzanne_va_show_conversation"):
        sc.suzanne_va_show_conversation = BoolProperty(
            name="Show Conversation Section",
            default=False,
        )
    if not hasattr(sc, "suzanne_va_show_recording"):
        sc.suzanne_va_show_recording = BoolProperty(
            name="Show Voice Section",
            default=True,
        )
    if not hasattr(sc, "suzanne_va_show_output"):
        sc.suzanne_va_show_output = BoolProperty(
            name="Show Latest Output Section",
            default=True,
        )
    if not hasattr(sc, "suzanne_va_output_view"):
        sc.suzanne_va_output_view = EnumProperty(
            name="Output View",
            description="Choose whether to show the latest response or transcript",
            items=[
                ("response", "Response", "Show latest ChatGPT response"),
                ("transcript", "Transcript", "Show latest transcript/prompt"),
            ],
            default="response",
        )
    if not hasattr(sc, "suzanne_va_expand_transcript"):
        sc.suzanne_va_expand_transcript = BoolProperty(
            name="Expand Transcript",
            default=False,
        )
    if not hasattr(sc, "suzanne_va_expand_response"):
        sc.suzanne_va_expand_response = BoolProperty(
            name="Expand Response",
            default=False,
        )
    if not hasattr(sc, "suzanne_va_conversation_preview"):
        sc.suzanne_va_conversation_preview = CollectionProperty(
            name="Conversation Preview",
            type=SUZANNEVA_PG_conversation_preview_item,
        )
    if not hasattr(sc, "suzanne_va_conversation_preview_index"):
        sc.suzanne_va_conversation_preview_index = IntProperty(
            name="Conversation Preview Index",
            default=0,
            min=0,
        )


def clear_props():
    sc = bpy.types.Scene
    for prop_name in _SCENE_PROP_NAMES:
        if hasattr(sc, prop_name):
            delattr(sc, prop_name)
