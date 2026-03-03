from tests.test_support import load_suzanne_modules


def test_state_ensure_props_registers_expected_scene_properties_and_is_idempotent():
    modules = load_suzanne_modules()
    scene_type = modules.bpy.types.Scene

    modules.state.ensure_props()
    first_status_prop = scene_type.suzanne_va_status

    assert first_status_prop["default"] == "Idle"
    assert scene_type.suzanne_va_context_turns["min"] == 1
    assert scene_type.suzanne_va_context_turns["max"] == 20
    assert scene_type.suzanne_va_output_view["default"] == "response"
    assert (
        scene_type.suzanne_va_conversation_preview["type"]
        is modules.state.SUZANNEVA_PG_conversation_preview_item
    )

    modules.state.ensure_props()

    assert scene_type.suzanne_va_status is first_status_prop


def test_state_clear_props_removes_registered_scene_properties():
    modules = load_suzanne_modules()
    scene_type = modules.bpy.types.Scene

    modules.state.ensure_props()
    modules.state.clear_props()

    for prop_name in modules.state._SCENE_PROP_NAMES:
        assert not hasattr(scene_type, prop_name)
