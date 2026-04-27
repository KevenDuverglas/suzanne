bl_info = {
    "name": "Suzanne Voice Assistant",
    "author": "Keven Michel Duverglas",
    "version": (1, 8, 5),
    "blender": (5, 0, 0),
    "location": "3D Viewport > N-Panel > Suzanne VA",
    "description": "Blender-focused chat + voice assistant with local conversation memory and context tools.",
    "category": "3D View",
}

try:
    import bpy
except ModuleNotFoundError:
    bpy = None

if bpy is not None:
    from .common import _ensure_recordings_dir
    from .state import ensure_props, clear_props
    from .preferences import SUZANNEVA_Preferences
    from .operators import (
        SUZANNEVA_OT_microphone_press,
        SUZANNEVA_OT_test_api_key,
        SUZANNEVA_OT_send_message,
        SUZANNEVA_OT_refresh_models,
        SUZANNEVA_OT_refresh_devices,
        SUZANNEVA_OT_clear_saved_api_key,
        SUZANNEVA_OT_copy_last_error,
        SUZANNEVA_OT_open_recordings_folder,
        SUZANNEVA_OT_test_microphone,
        SUZANNEVA_OT_test_transcription,
        SUZANNEVA_OT_new_conversation,
        SUZANNEVA_OT_rename_conversation,
        SUZANNEVA_OT_delete_conversation,
    )
    from .panel import SUZANNEVA_PT_sidebar

    classes = (
        SUZANNEVA_Preferences,
        SUZANNEVA_OT_microphone_press,
        SUZANNEVA_OT_test_api_key,
        SUZANNEVA_OT_send_message,
        SUZANNEVA_OT_refresh_models,
        SUZANNEVA_OT_refresh_devices,
        SUZANNEVA_OT_clear_saved_api_key,
        SUZANNEVA_OT_copy_last_error,
        SUZANNEVA_OT_open_recordings_folder,
        SUZANNEVA_OT_test_microphone,
        SUZANNEVA_OT_test_transcription,
        SUZANNEVA_OT_new_conversation,
        SUZANNEVA_OT_rename_conversation,
        SUZANNEVA_OT_delete_conversation,
        SUZANNEVA_PT_sidebar,
    )
else:
    classes = ()


def register():
    if bpy is None:
        raise RuntimeError("Suzanne Voice Assistant must be registered from Blender.")
    for cls in classes:
        bpy.utils.register_class(cls)
    ensure_props()
    _ensure_recordings_dir()


def unregister():
    if bpy is None:
        return
    clear_props()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
