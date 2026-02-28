from .common import *  # noqa: F403,F401

# --------------------------- operator --------------------------

class SUZANNEVA_OT_microphone_press(Operator):
    """Single Microphone button: press to switch ON/OFF"""
    bl_idname = "suzanne_va.microphone_press"
    bl_label = "Microphone"
    bl_options = {'REGISTER', 'UNDO'}

    recording_process = None
    recording_path = ""

    def _ffmpeg_path(self):
        return _resolve_ffmpeg_path()

    def _atunc_path(self):
        candidate = _addon_dir() / "atunc" / "atunc"
        if candidate.exists():
            return str(candidate)
        return None

    def _get_recording_path(self, context):
        prefs = _get_addon_preferences(context)
        if not _ensure_recordings_dir():
            # Fallback to a temp folder if add-on dir isn't writable.
            temp_dir = pathlib.Path(tempfile.gettempdir()) / "suzanne_va_recordings"
            temp_dir.mkdir(parents=True, exist_ok=True)
            recordings_dir = temp_dir
        else:
            recordings_dir = _recordings_dir()
        timestamp = _now_timestamp()
        filename = f"{prefs.file_prefix}{timestamp}.wav"
        return str(recordings_dir / filename)

    def _recording_output_args(self):
        return [
            "-ac", "1",
            "-ar", "16000",
            "-blocksize", "2048",
            "-flush_packets", "1",
            SUZANNEVA_OT_microphone_press.recording_path,
        ]

    def _start_process_with_candidates(self, candidates):
        last_error = ""
        for args in candidates:
            _log(f"Starting recording: {' '.join(args)}")
            proc = Popen(args, stdout=PIPE, stderr=PIPE)
            time.sleep(0.35)
            if proc.poll() is None:
                SUZANNEVA_OT_microphone_press.recording_process = proc
                return True, ""
            try:
                _out, err = proc.communicate(timeout=0.2)
            except Exception:
                err = b""
            if err:
                last_error = err.decode("utf-8", errors="replace").strip().splitlines()[-1]
            else:
                last_error = "recorder process exited immediately."
            _log(f"Recording candidate failed: {last_error}")
        return False, last_error

    def _start_recording(self, context):
        os_platform = platform.system()

        SUZANNEVA_OT_microphone_press.recording_path = self._get_recording_path(context)
        try:
            prefs = _get_addon_preferences(context)
            if prefs.audio_input_device != _SYSTEM_AUDIO_DEVICE_ID:
                prefs.audio_input_device = _SYSTEM_AUDIO_DEVICE_ID
        except Exception:
            pass

        if os_platform == "Darwin":
            atunc_path = self._atunc_path()
            if not atunc_path:
                self.report({'ERROR'}, "atunc not found for macOS recording")
                return False
            candidates = [[
                atunc_path,
                "--device-id",
                "default",
                "--output-path",
                SUZANNEVA_OT_microphone_press.recording_path,
            ]]
            fallback_device = _first_non_default_audio_device(_get_audio_devices_macos())
            if fallback_device:
                candidates.append([
                    atunc_path,
                    "--device-id",
                    fallback_device,
                    "--output-path",
                    SUZANNEVA_OT_microphone_press.recording_path,
                ])
        else:
            ffmpeg_path = self._ffmpeg_path()
            if not ffmpeg_path:
                self.report({'ERROR'}, "ffmpeg unavailable. Bundle it with Suzanne or install it on PATH.")
                return False

            if os_platform == "Linux":
                candidates = [
                    [ffmpeg_path, "-f", "alsa", "-i", "default"] + self._recording_output_args(),
                    [ffmpeg_path, "-f", "pulse", "-i", "default"] + self._recording_output_args(),
                ]
            elif os_platform == "Windows":
                candidates = [
                    [ffmpeg_path, "-f", "wasapi", "-i", "default"] + self._recording_output_args(),
                    [ffmpeg_path, "-f", "dshow", "-i", "audio=default"] + self._recording_output_args(),
                ]
                fallback_device = _first_non_default_audio_device(_get_audio_devices_windows())
                if fallback_device:
                    candidates.append(
                        [ffmpeg_path, "-f", "dshow", "-i", f"audio={fallback_device}"] + self._recording_output_args()
                    )
            else:
                candidates = [
                    [ffmpeg_path, "-f", "alsa", "-i", "default"] + self._recording_output_args(),
                ]

        success, failure_reason = self._start_process_with_candidates(candidates)
        if success:
            return True

        if failure_reason:
            self.report({'ERROR'}, f"Could not start recording: {failure_reason}")
        else:
            self.report({'ERROR'}, "Could not start recording with system default microphone.")
        return False

    def _stop_recording(self):
        if not SUZANNEVA_OT_microphone_press.recording_process:
            return
        SUZANNEVA_OT_microphone_press.recording_process.terminate()
        try:
            SUZANNEVA_OT_microphone_press.recording_process.wait(timeout=3)
        except TimeoutExpired:
            SUZANNEVA_OT_microphone_press.recording_process.kill()
        SUZANNEVA_OT_microphone_press.recording_process = None

    def _wait_for_file(self, path, timeout_s=2.0):
        start = time.time()
        while time.time() - start < timeout_s:
            if path and os.path.exists(path):
                return True
            time.sleep(0.1)
        return False

    def _send_to_chatgpt(self, context, audio_path):
        prefs = _get_addon_preferences(context)
        api_key = _get_effective_api_key(prefs)
        if not api_key:
            return False, "Missing OpenAI API key in add-on preferences."

        if not audio_path or not os.path.exists(audio_path):
            return False, f"Recording file not found: {audio_path}"

        try:
            transcription = _transcribe_audio(
                api_key,
                prefs.transcription_model,
                audio_path,
            )
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            return False, f"Transcription failed: {exc}"

        transcript_text = transcription.get("text", "")
        if not transcript_text:
            return False, "Transcription returned no text."

        scene = context.scene
        info_context = ""
        if scene.suzanne_va_include_info_history:
            info_context = _get_info_history_lines(_INFO_HISTORY_LINE_LIMIT)
            scene.suzanne_va_last_info_history = info_context or "(No Info history was captured.)"
        else:
            scene.suzanne_va_last_info_history = ""
        conversation_context = _conversation_context_block(scene)

        prompt_text = _build_markdown_input(
            transcript_text,
            info_context,
            is_voice=True,
            conversation_context_text=conversation_context,
        )
        prompt_text = _blender_only_prefix(prompt_text)

        try:
            response = _call_chatgpt(
                api_key,
                prefs.response_model,
                prompt_text,
            )
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            return False, f"ChatGPT request failed: {exc}"

        response_text = response.get("output_text")
        if not response_text:
            output_items = response.get("output", [])
            response_text = ""
            for item in output_items:
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            response_text += content.get("text", "")

        scene.suzanne_va_last_audio = audio_path
        scene.suzanne_va_last_transcript = transcript_text
        scene.suzanne_va_last_response = response_text or ""
        scene.suzanne_va_expand_transcript = False
        scene.suzanne_va_expand_response = False
        _append_conversation_exchange(scene, transcript_text, response_text or "", source="voice")

        return True, ""

    def execute(self, context):
        scene = context.scene
        # Flip the scene flag
        scene.suzanne_va_mic_active = not scene.suzanne_va_mic_active

        if scene.suzanne_va_mic_active:
            if not self._start_recording(context):
                scene.suzanne_va_mic_active = False
                scene.suzanne_va_status = "Idle"
                _tag_redraw_all()
                return {'CANCELLED'}

            scene.suzanne_va_status = "Recording..."
            self.report({'INFO'}, "Suzanne VA: Recording started")
            _log("Mic -> ON (recording)")
        else:
            scene.suzanne_va_status = "Stopping..."
            _tag_redraw_all()

            self._stop_recording()

            recording_path = SUZANNEVA_OT_microphone_press.recording_path
            if not self._wait_for_file(recording_path):
                scene.suzanne_va_status = "Idle (error)"
                self.report(
                    {'ERROR'},
                    f"Suzanne VA: Recording file not found: {recording_path}",
                )
                _log(f"Mic -> OFF (error: file not found: {recording_path})")
                _tag_redraw_all()
                return {'FINISHED'}

            scene.suzanne_va_status = "Sending to ChatGPT..."
            success, message = self._send_to_chatgpt(
                context,
                recording_path,
            )
            if success:
                scene.suzanne_va_status = "Idle (sent)"
                self.report({'INFO'}, "Suzanne VA: Sent to ChatGPT")
                _log("Mic -> OFF (sent)")
            else:
                scene.suzanne_va_status = "Idle (error)"
                self.report({'ERROR'}, f"Suzanne VA: {message}")
                _log(f"Mic -> OFF (error: {message})")

        _tag_redraw_all()
        return {'FINISHED'}

# ------------------------ send message -------------------------

class SUZANNEVA_OT_send_message(Operator):
    bl_idname = "suzanne_va.send_message"
    bl_label = "Send Message"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        prompt = (scene.suzanne_va_prompt or "").strip()
        if not prompt:
            self.report({'ERROR'}, "Please type a message first.")
            return {'CANCELLED'}

        prefs = _get_addon_preferences(context)
        api_key = _get_effective_api_key(prefs)
        if not api_key:
            self.report({'ERROR'}, "Missing OpenAI API key in add-on preferences.")
            return {'CANCELLED'}

        info_context = ""
        if scene.suzanne_va_include_info_history:
            info_context = _get_info_history_lines(_INFO_HISTORY_LINE_LIMIT)
            scene.suzanne_va_last_info_history = info_context or "(No Info history was captured.)"
        else:
            scene.suzanne_va_last_info_history = ""
        conversation_context = _conversation_context_block(scene)

        prompt_text = _build_markdown_input(
            prompt,
            info_context,
            is_voice=False,
            conversation_context_text=conversation_context,
        )
        prompt_text = _blender_only_prefix(prompt_text)

        scene.suzanne_va_status = "Sending..."
        _tag_redraw_all()

        try:
            response = _call_chatgpt(
                api_key,
                prefs.response_model,
                prompt_text,
            )
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            scene.suzanne_va_status = "Idle (error)"
            self.report({'ERROR'}, f"Send failed: {exc}")
            _tag_redraw_all()
            return {'CANCELLED'}

        response_text = response.get("output_text")
        if not response_text:
            output_items = response.get("output", [])
            response_text = ""
            for item in output_items:
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            response_text += content.get("text", "")

        scene.suzanne_va_last_transcript = prompt
        scene.suzanne_va_last_response = response_text or ""
        scene.suzanne_va_expand_transcript = False
        scene.suzanne_va_expand_response = False
        _append_conversation_exchange(scene, prompt, response_text or "", source="text")
        scene.suzanne_va_status = "Idle (sent)"
        _tag_redraw_all()
        return {'FINISHED'}

# ------------------------- test key ----------------------------

class SUZANNEVA_OT_test_api_key(Operator):
    """Test OpenAI API key via a lightweight models call."""
    bl_idname = "suzanne_va.test_api_key"
    bl_label = "Test API Key"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        api_key = _get_effective_api_key(prefs)
        if not api_key:
            _set_diagnostics_message(prefs, error="OpenAI API key is empty.")
            self.report({'ERROR'}, "OpenAI API key is empty.")
            return {'CANCELLED'}
        _log(f"API key length: {len(api_key)}")
        if not api_key.startswith("sk-"):
            _set_diagnostics_message(prefs, error="OpenAI API key must start with 'sk-'.")
            self.report({'ERROR'}, "OpenAI API key must start with 'sk-'.")
            return {'CANCELLED'}

        try:
            response_text = _get_json(
                "https://api.openai.com/v1/models",
                api_key,
            )
            _ = json.loads(response_text)
        except HTTPError as exc:
            body = _read_http_error_body(exc)
            message = f"API key test failed: HTTP {exc.code}"
            if body:
                message += f" | {body}"
            _set_diagnostics_message(prefs, error=message)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        except URLError as exc:
            _set_diagnostics_message(prefs, error=f"API key test failed: {exc}")
            self.report({'ERROR'}, f"API key test failed: {exc}")
            return {'CANCELLED'}
        except json.JSONDecodeError:
            _set_diagnostics_message(prefs, error="API key test failed: invalid JSON response")
            self.report({'ERROR'}, "API key test failed: invalid JSON response")
            return {'CANCELLED'}

        _set_diagnostics_message(prefs, message="API key is valid.")
        self.report({'INFO'}, "API key is valid.")
        return {'FINISHED'}

# ------------------------ refresh lists ------------------------

class SUZANNEVA_OT_refresh_models(Operator):
    bl_idname = "suzanne_va.refresh_models"
    bl_label = "Refresh Models"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        api_key = _get_effective_api_key(prefs)
        _get_models_cached(api_key, force=True)
        _set_diagnostics_message(prefs, message="Model list refreshed.")
        self.report({'INFO'}, "Model list refreshed.")
        return {'FINISHED'}

class SUZANNEVA_OT_refresh_devices(Operator):
    bl_idname = "suzanne_va.refresh_devices"
    bl_label = "Refresh Devices"
    bl_options = {'REGISTER'}

    def execute(self, context):
        _AUDIO_DEVICES_CACHE["ts"] = 0.0
        _AUDIO_DEVICES_CACHE["items"] = []
        self.report({'INFO'}, "Audio devices refreshed.")
        return {'FINISHED'}

class SUZANNEVA_OT_clear_saved_api_key(Operator):
    bl_idname = "suzanne_va.clear_saved_api_key"
    bl_label = "Clear Saved API Key"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        prefs.api_key = ""
        prefs.show_api_key = False
        _set_diagnostics_message(prefs, message="Saved API key cleared.")
        self.report({'INFO'}, "Saved API key cleared.")
        return {'FINISHED'}

class SUZANNEVA_OT_copy_last_error(Operator):
    bl_idname = "suzanne_va.copy_last_error"
    bl_label = "Copy Last Error"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        error_text = (prefs.diagnostics_last_error or "").strip()
        if not error_text:
            self.report({'ERROR'}, "No diagnostics error to copy.")
            return {'CANCELLED'}
        context.window_manager.clipboard = error_text
        self.report({'INFO'}, "Copied last error to clipboard.")
        return {'FINISHED'}

class SUZANNEVA_OT_open_recordings_folder(Operator):
    bl_idname = "suzanne_va.open_recordings_folder"
    bl_label = "Open Recordings Folder"
    bl_options = {'REGISTER'}

    def execute(self, _context):
        _ensure_recordings_dir()
        folder = _recordings_dir()
        if not _show_file_in_os(folder):
            self.report({'ERROR'}, "Could not open recordings folder.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Opened recordings folder.")
        return {'FINISHED'}

class SUZANNEVA_OT_test_microphone(Operator):
    bl_idname = "suzanne_va.test_microphone"
    bl_label = "Test Microphone"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        success, detail = _run_microphone_probe()
        if not success:
            _set_diagnostics_message(prefs, error=f"Microphone test failed: {detail}")
            self.report({'ERROR'}, f"Microphone test failed: {detail}")
            return {'CANCELLED'}

        _set_diagnostics_message(prefs, message=f"Microphone test passed: {detail}")
        self.report({'INFO'}, "Microphone test passed.")
        return {'FINISHED'}

class SUZANNEVA_OT_test_transcription(Operator):
    bl_idname = "suzanne_va.test_transcription"
    bl_label = "Test Transcription"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = _get_addon_preferences(context)
        api_key = _get_effective_api_key(prefs)
        if not api_key:
            message = "Missing OpenAI API key for transcription test."
            _set_diagnostics_message(prefs, error=message)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temp_wav = handle.name

        try:
            _write_silence_wav(temp_wav)
            response = _transcribe_audio(
                api_key,
                prefs.transcription_model,
                temp_wav,
            )
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            message = f"Transcription test failed: {exc}"
            _set_diagnostics_message(prefs, error=message)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        except Exception as exc:
            message = f"Transcription test failed: {exc}"
            _set_diagnostics_message(prefs, error=message)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        finally:
            try:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
            except Exception:
                pass

        if not isinstance(response, dict):
            message = "Transcription test failed: invalid response format."
            _set_diagnostics_message(prefs, error=message)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        text = str(response.get("text", "") or "").strip()
        if text:
            message = f"Transcription test passed. Returned text: {_clip_text(text, 80)}"
        else:
            message = "Transcription test passed. Empty text is expected for silence."
        _set_diagnostics_message(prefs, message=message)
        self.report({'INFO'}, "Transcription test passed.")
        return {'FINISHED'}

class SUZANNEVA_OT_new_conversation(Operator):
    bl_idname = "suzanne_va.new_conversation"
    bl_label = "New Conversation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        seed = (scene.suzanne_va_prompt or "").strip()
        conversation = _new_conversation(scene, title_seed=seed)
        if not conversation:
            self.report({'ERROR'}, "Could not create a local conversation.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Created conversation: {conversation.get('title', 'Untitled')}")
        _tag_redraw_all()
        return {'FINISHED'}

class SUZANNEVA_OT_rename_conversation(Operator):
    bl_idname = "suzanne_va.rename_conversation"
    bl_label = "Rename Conversation"
    bl_options = {'REGISTER', 'UNDO'}

    new_title: StringProperty(
        name="Title",
        description="New title for this conversation",
        default="",
    )

    def invoke(self, context, _event):
        scene = context.scene
        conversation, _ = _get_active_conversation(scene, create_if_missing=False)
        if not conversation:
            self.report({'ERROR'}, "No conversation selected.")
            return {'CANCELLED'}
        self.new_title = str(conversation.get("title") or "")
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, _context):
        self.layout.prop(self, "new_title", text="Title")

    def execute(self, context):
        if not _rename_conversation(context.scene, self.new_title):
            self.report({'ERROR'}, "Could not rename conversation.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Conversation renamed.")
        _tag_redraw_all()
        return {'FINISHED'}

class SUZANNEVA_OT_delete_conversation(Operator):
    bl_idname = "suzanne_va.delete_conversation"
    bl_label = "Delete Conversation"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if not _delete_active_conversation(context.scene):
            self.report({'ERROR'}, "Could not delete conversation.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Conversation deleted.")
        _tag_redraw_all()
        return {'FINISHED'}
