import bpy
from bpy.types import Operator, Panel, AddonPreferences
from bpy.props import BoolProperty, StringProperty, EnumProperty, IntProperty
import datetime
import json
import mimetypes
import os
import tempfile
import time
import pathlib
import platform
import shlex
import shutil
import uuid
from subprocess import Popen, PIPE, DEVNULL, TimeoutExpired
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import textwrap
import re
import subprocess
import wave

_SYNCING_API_KEY = False
_MODELS_CACHE = {"ts": 0.0, "ids": []}
_MODEL_ENUM_ITEMS_CACHE = []
_TRANSCRIBE_ENUM_ITEMS_CACHE = []
_AUDIO_DEVICES_CACHE = {"ts": 0.0, "items": []}
_CONVERSATION_ENUM_ITEMS_CACHE = []
_INFO_HISTORY_LINE_LIMIT = 100
_SYSTEM_AUDIO_DEVICE_ID = "system_default"
_TRANSCRIPT_PREVIEW_LINES = 8
_RESPONSE_PREVIEW_LINES = 12
_NO_CONVERSATION_ID = "__none__"
_CONVERSATION_FILE_NAME = "suzanne_conversations.json"
_CONVERSATION_MESSAGE_CHAR_LIMIT = 500
_FFMPEG_ENV_VAR = "SUZANNE_FFMPEG_PATH"
ADDON_MODULE = (__package__.split(".")[0] if __package__ else __name__.split(".")[0])

# ---------------------------- utils ----------------------------

def _tag_redraw_all():
    wm = bpy.context.window_manager
    for win in wm.windows:
        scr = win.screen
        if not scr:
            continue
        for area in scr.areas:
            area.tag_redraw()

def _wrap_ui_text(text, width=70):
    if not text:
        return [""]
    lines = []
    for raw_line in str(text).splitlines():
        if not raw_line.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw_line, width=width, replace_whitespace=False))
    return lines

def _clean_markdown(text):
    if not text:
        return ""
    cleaned_lines = []
    for raw in str(text).splitlines():
        line = raw.strip()
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("*", "").replace("`", "")
        line = re.sub(r"^[-•]\s+", "• ", line)
        line = re.sub(r"^\d+\.\s+", lambda m: f"{m.group(0).replace('. ', ') ')}", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()

def _response_lines(text, width=80):
    return _wrap_ui_text(_clean_markdown(text), width=width)

def _preview_response_lines(text, width=80, max_lines=10, expanded=False):
    full_lines = _response_lines(text, width=width)
    needs_toggle = len(full_lines) > max_lines
    if expanded or not needs_toggle:
        return full_lines, needs_toggle
    return full_lines[:max_lines], needs_toggle

def _bundled_ffmpeg_candidates():
    bin_dir = _addon_dir() / "bin"
    os_platform = platform.system()
    if os_platform == "Windows":
        return [
            bin_dir / "windows" / "ffmpeg.exe",
            bin_dir / "ffmpeg.exe",
        ]
    if os_platform == "Darwin":
        return [
            bin_dir / "macos" / "ffmpeg",
            bin_dir / "ffmpeg",
        ]
    return [
        bin_dir / "linux" / "ffmpeg",
        bin_dir / "ffmpeg",
    ]

def _resolve_ffmpeg_path():
    override = str(os.environ.get(_FFMPEG_ENV_VAR, "") or "").strip().strip('"')
    if override:
        override_path = pathlib.Path(override)
        if override_path.exists():
            return str(override_path)

    for candidate in _bundled_ffmpeg_candidates():
        if candidate.exists():
            return str(candidate)

    return shutil.which("ffmpeg")

def _set_enum_items_cache(cache, items):
    # Blender can crash if enum callbacks return short-lived Python strings.
    cache[:] = [
        (str(identifier), str(name), str(description))
        for identifier, name, description in items
    ]
    return cache

def _status_visual(status_text, is_recording):
    status = (status_text or "").strip() or "Idle"
    normalized = status.lower()
    if is_recording:
        return status, "REC", True
    if "error" in normalized:
        return status, "ERROR", True
    if "sending" in normalized or "stopping" in normalized:
        return status, "TIME", False
    if "sent" in normalized:
        return status, "CHECKMARK", False
    return status, "INFO", False

def _draw_section_header(box, scene, prop_name, title, icon):
    row = box.row(align=True)
    is_open = bool(getattr(scene, prop_name, True))
    row.prop(
        scene,
        prop_name,
        text="",
        icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT',
        emboss=False,
    )
    row.label(text=title, icon=icon)
    return is_open

def _draw_expand_toggle(layout, scene, prop_name):
    is_expanded = bool(getattr(scene, prop_name, False))
    layout.prop(
        scene,
        prop_name,
        text="Show less" if is_expanded else "Show more",
        icon='TRIA_UP' if is_expanded else 'TRIA_DOWN',
        emboss=False,
    )

def _blender_only_prefix(text):
    return (
        "Answer only about Blender. If the question is unrelated to Blender, "
        "say you can only help with Blender and ask them to rephrase for Blender.\n\n"
        f"User question: {text}"
    )

def _tail_lines(text, limit):
    if not text:
        return ""
    lines = str(text).splitlines()
    if limit <= 0:
        return ""
    return "\n".join(lines[-limit:])

def _merge_tail_lines(primary_block, secondary_block, limit):
    if limit <= 0:
        return ""
    primary_lines = []
    for raw_line in str(primary_block or "").splitlines():
        line = raw_line.rstrip()
        if line.strip():
            primary_lines.append(line)

    secondary_lines = []
    primary_seen = set(primary_lines)
    for raw_line in str(secondary_block or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line in primary_seen:
            continue
        secondary_lines.append(line)

    merged = primary_lines + secondary_lines
    if not merged:
        return ""
    return "\n".join(merged[-limit:])

def _history_guidance_block():
    return (
        "## Assistant Guidance\n"
        "When Blender Session History is provided, use it to interpret the user's question.\n"
        "- Treat the history as recent context and prioritize the newest relevant lines.\n"
        "- Translate Blender operator/API lines into plain language.\n"
        "- If asked what happened, summarize recent actions in time order.\n"
        "- Clearly separate confirmed facts from likely inferences.\n"
        "- If details are missing, say what is uncertain and ask one focused follow-up."
    )

def _find_area_context(area_type):
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != area_type:
                continue
            region = None
            for candidate in area.regions:
                if candidate.type == "WINDOW":
                    region = candidate
                    break
            if region:
                return {
                    "window": window,
                    "screen": screen,
                    "area": area,
                    "region": region,
                }
    return None

def _enable_info_filters(area):
    try:
        space = area.spaces.active
    except Exception:
        return
    if not space:
        return

    for prop_name in (
        "show_report_debug",
        "show_report_info",
        "show_report_operator",
        "show_report_warning",
        "show_report_error",
    ):
        if hasattr(space, prop_name):
            try:
                setattr(space, prop_name, True)
            except Exception:
                pass

def _copy_info_reports_with_override(override_ctx):
    wm = bpy.context.window_manager
    area = override_ctx.get("area")
    if area:
        _enable_info_filters(area)
    with bpy.context.temp_override(**override_ctx):
        bpy.ops.info.select_all(action='SELECT')
        bpy.ops.info.report_copy()
    return wm.clipboard or ""

def _copy_info_reports_with_temp_area():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            original_type = area.type
            try:
                area.type = "INFO"
                region = None
                for candidate in area.regions:
                    if candidate.type == "WINDOW":
                        region = candidate
                        break
                if not region:
                    continue
                override_ctx = {
                    "window": window,
                    "screen": screen,
                    "area": area,
                    "region": region,
                }
                report_text = _copy_info_reports_with_override(override_ctx)
                if report_text:
                    return report_text
            except Exception as exc:
                _log(f"Could not copy INFO history via temp area: {exc}")
            finally:
                try:
                    area.type = original_type
                except Exception:
                    pass
    return ""

def _operator_snapshot_lines(limit):
    lines = []
    try:
        for op in bpy.context.window_manager.operators:
            op_name = getattr(op, "bl_idname", "") or getattr(op.bl_rna, "identifier", "")
            if not op_name:
                continue

            prop_chunks = []
            bl_rna = getattr(op, "bl_rna", None)
            if bl_rna:
                for prop in bl_rna.properties:
                    prop_id = prop.identifier
                    if prop_id == "rna_type" or getattr(prop, "is_readonly", False):
                        continue
                    try:
                        value = getattr(op, prop_id)
                    except Exception:
                        continue
                    if value in ("", None):
                        continue
                    try:
                        if value == prop.default:
                            continue
                    except Exception:
                        pass
                    prop_chunks.append(f"{prop_id}={value!r}")

            if prop_chunks:
                lines.append(f"{op_name}({', '.join(prop_chunks)})")
            else:
                lines.append(op_name)
    except Exception as exc:
        _log(f"Operator fallback failed: {exc}")

    return _tail_lines("\n".join(lines), limit)

def _get_info_history_lines(limit=_INFO_HISTORY_LINE_LIMIT):
    """
    Best-effort copy of the Info editor report history.
    Also merges a lightweight operator snapshot for extra context when possible.
    """
    wm = bpy.context.window_manager
    original_clipboard = wm.clipboard
    report_text = ""

    info_override = _find_area_context("INFO")
    if info_override:
        try:
            report_text = _copy_info_reports_with_override(info_override)
        except Exception as exc:
            _log(f"Could not copy INFO history: {exc}")

    if not report_text:
        report_text = _copy_info_reports_with_temp_area()

    wm.clipboard = original_clipboard

    operator_snapshot = _operator_snapshot_lines(limit)
    return _merge_tail_lines(report_text, operator_snapshot, limit=limit)

def _build_markdown_input(
    user_text,
    context_text,
    is_voice=False,
    conversation_context_text="",
):
    user_header = "Voice Transcript" if is_voice else "User Prompt"
    sections = []

    if conversation_context_text:
        sections.append(conversation_context_text)

    sections.append(f"## {user_header}\n{(user_text or '').strip()}")

    if context_text:
        sections.insert(0, _history_guidance_block())
        sections.append(
            "## Blender Session History (last 100 lines)\n"
            "```text\n"
            f"{context_text}\n"
            "```"
        )

    return "\n\n".join(sections).strip()

def _get_models_from_api(api_key):
    if not api_key:
        return []
    try:
        response_text = _get_json("https://api.openai.com/v1/models", api_key)
        data = json.loads(response_text).get("data", [])
        ids = [m.get("id") for m in data if m.get("id")]
        ids = sorted(set(ids))
        return ids
    except Exception:
        return []

def _get_models_cached(api_key, force=False):
    if force:
        _MODELS_CACHE["ids"] = _get_models_from_api(api_key)
        _MODELS_CACHE["ts"] = time.time()
    return list(_MODELS_CACHE["ids"])

def _model_enum_items(self, context):
    prefs = _get_addon_preferences(context)
    ids = _get_models_cached(_get_effective_api_key(prefs))
    if not ids:
        ids = ["gpt-4o-mini"]
    return _set_enum_items_cache(
        _MODEL_ENUM_ITEMS_CACHE,
        [(m, m, "") for m in ids],
    )

def _transcribe_model_enum_items(self, context):
    prefs = _get_addon_preferences(context)
    ids = _get_models_cached(_get_effective_api_key(prefs))
    transcribe_ids = [
        m for m in ids
        if "transcribe" in m or m == "whisper-1"
    ]
    if not transcribe_ids:
        transcribe_ids = ["gpt-4o-mini-transcribe", "whisper-1"]
    return _set_enum_items_cache(
        _TRANSCRIBE_ENUM_ITEMS_CACHE,
        [(m, m, "") for m in transcribe_ids],
    )

def _get_audio_devices_linux():
    arecord = shutil.which("arecord")
    if not arecord:
        return [("default", "default", "default")]
    try:
        proc = subprocess.Popen([arecord, "-L"], stdout=PIPE, stderr=PIPE)
        out, _ = proc.communicate(timeout=2)
    except Exception:
        return [("default", "default", "default")]
    items = []
    for line in out.splitlines():
        try:
            text = line.decode("utf-8").strip()
        except Exception:
            continue
        if not text or text.startswith(" "):
            continue
        if text in {"null", "oss", "pulse", "pipewire", "speex", "speexrate", "samplerate", "lavrate"}:
            continue
        items.append((text, text, text))
    if not items:
        items = [("default", "default", "default")]
    return items

def _get_audio_devices_windows():
    ffmpeg = _resolve_ffmpeg_path()
    if not ffmpeg:
        return [("default", "default", "default")]
    try:
        args = [ffmpeg] + shlex.split("-f dshow -list_devices true -hide_banner -i dummy")
        proc = subprocess.Popen(args, stdout=PIPE, stderr=PIPE)
        _, err = proc.communicate(timeout=2)
    except Exception:
        return [("default", "default", "default")]
    lines = err.splitlines()
    devices = []
    grouped = False
    for raw in lines:
        try:
            text = raw.decode("utf-8")
        except Exception:
            continue
        if "DirectShow audio devices" in text:
            grouped = True
            continue
        if text.endswith("(audio)"):
            grouped = False
        if grouped:
            if "Alternative name" in text or "Error" in text:
                continue
        if "(audio)" in text or grouped:
            matches = re.findall(r'"(.+?)"', text)
            if matches:
                for m in matches:
                    devices.append((m, m, m))
    if not devices:
        devices = [("default", "default", "default")]
    return devices

def _get_audio_devices_macos():
    atunc = _addon_dir() / "atunc" / "atunc"
    if not atunc.exists():
        return [("default", "default", "default")]
    try:
        proc = subprocess.Popen([str(atunc), "--list-devices"], stdout=PIPE, stderr=PIPE)
        out, _ = proc.communicate(timeout=2)
        data = json.loads(out)
    except Exception:
        return [("default", "default", "default")]
    items = []
    for entry in data:
        device_id = str(entry.get("id"))
        name = entry.get("name", device_id)
        items.append((device_id, name, name))
    if not items:
        items = [("default", "default", "default")]
    return items

def _first_non_default_audio_device(items):
    for dev_id, _label, _desc in items:
        device = str(dev_id or "").strip()
        if not device:
            continue
        if device.lower() == "default":
            continue
        return device
    return ""

def _os_display_name():
    os_platform = platform.system()
    if os_platform == "Darwin":
        return "macOS"
    if os_platform:
        return os_platform
    return "Unknown"

def _get_addon_preferences(context=None):
    ctx = context or bpy.context
    try:
        addon_entry = ctx.preferences.addons.get(ADDON_MODULE)
    except Exception:
        addon_entry = None
    if addon_entry:
        return addon_entry.preferences
    return None

def _get_effective_api_key(prefs):
    if not prefs:
        return ""
    return (prefs.api_key or "").strip()

def _set_diagnostics_message(prefs, message="", error=""):
    if not prefs:
        return
    prefs.diagnostics_last_message = _clip_text(message, 240) if message else ""
    prefs.diagnostics_last_error = _clip_text(error, 260) if error else ""

def _show_file_in_os(path):
    try:
        bpy.ops.wm.path_open(filepath=str(path))
        return True
    except Exception as exc:
        _log(f"Could not open path in OS: {exc}")
        return False

def _microphone_probe_candidates(ffmpeg_path, output_path):
    common_tail = [
        "-t", "0.40",
        "-ac", "1",
        "-ar", "16000",
        "-y",
        output_path,
    ]
    os_platform = platform.system()
    if os_platform == "Linux":
        return [
            [ffmpeg_path, "-nostdin", "-f", "alsa", "-i", "default"] + common_tail,
            [ffmpeg_path, "-nostdin", "-f", "pulse", "-i", "default"] + common_tail,
        ]
    if os_platform == "Windows":
        candidates = [
            [ffmpeg_path, "-nostdin", "-f", "wasapi", "-i", "default"] + common_tail,
            [ffmpeg_path, "-nostdin", "-f", "dshow", "-i", "audio=default"] + common_tail,
        ]
        fallback_device = _first_non_default_audio_device(_get_audio_devices_windows())
        if fallback_device:
            candidates.append(
                [ffmpeg_path, "-nostdin", "-f", "dshow", "-i", f"audio={fallback_device}"] + common_tail
            )
        return candidates
    return [
        [ffmpeg_path, "-nostdin", "-f", "alsa", "-i", "default"] + common_tail,
    ]

def _run_microphone_probe():
    os_platform = platform.system()
    if os_platform == "Darwin":
        atunc_path = _addon_dir() / "atunc" / "atunc"
        if not atunc_path.exists():
            return False, "atunc is not installed."
        devices = _get_audio_devices_macos()
        if not devices:
            return False, "No macOS audio devices were detected."
        return True, f"atunc found with {len(devices)} detected device(s)."

    ffmpeg_path = _resolve_ffmpeg_path()
    if not ffmpeg_path:
        return False, "ffmpeg is unavailable. Bundle ffmpeg with Suzanne or install it on PATH."

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        probe_path = handle.name

    last_error = ""
    try:
        for args in _microphone_probe_candidates(ffmpeg_path, probe_path):
            try:
                proc = subprocess.run(
                    args,
                    stdout=DEVNULL,
                    stderr=PIPE,
                    timeout=8,
                )
            except Exception as exc:
                last_error = str(exc)
                continue

            if proc.returncode == 0 and os.path.exists(probe_path) and os.path.getsize(probe_path) > 44:
                return True, "Microphone capture probe succeeded."

            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            if stderr:
                last_error = stderr.splitlines()[-1]
    finally:
        try:
            if os.path.exists(probe_path):
                os.remove(probe_path)
        except Exception:
            pass

    return False, last_error or "Microphone capture probe failed."

def _write_silence_wav(path, duration_s=0.30, sample_rate=16000):
    frame_count = max(1, int(duration_s * sample_rate))
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)

def _audio_devices_enum_items(self, context):
    os_name = _os_display_name()
    label = f"System Default ({os_name})"

    _AUDIO_DEVICES_CACHE["items"] = _set_enum_items_cache(
        _AUDIO_DEVICES_CACHE["items"],
        [(
            _SYSTEM_AUDIO_DEVICE_ID,
            label,
            f"Use the {os_name} default microphone (with internal fallbacks).",
        )],
    )
    _AUDIO_DEVICES_CACHE["ts"] = time.time()

    return _AUDIO_DEVICES_CACHE["items"]


def _addon_dir():
    return pathlib.Path(__file__).parent.resolve()

def _recordings_dir():
    return _addon_dir() / "recordings"

def _ensure_recordings_dir():
    try:
        _recordings_dir().mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        _log(f"Could not create recordings dir in add-on folder: {exc}")
        return False

def _now_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def _now_iso_timestamp():
    return datetime.datetime.now().isoformat(timespec="seconds")

def _conversation_storage_dir():
    preferred = _addon_dir() / "data"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError as exc:
        _log(f"Could not create data dir in add-on folder: {exc}")

    fallback = pathlib.Path(tempfile.gettempdir()) / "suzanne_va_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

def _conversation_store_path():
    return _conversation_storage_dir() / _CONVERSATION_FILE_NAME

def _empty_conversation_store():
    return {
        "version": 1,
        "conversations": [],
    }

def _clip_text(text, limit):
    value = str(text or "").strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."

def _conversation_title_from_seed(seed_text):
    first_line = ""
    for line in str(seed_text or "").splitlines():
        candidate = line.strip()
        if candidate:
            first_line = candidate
            break
    if first_line:
        return _clip_text(first_line, 48)
    return f"Conversation {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"

def _normalize_conversation(raw):
    if not isinstance(raw, dict):
        return None

    conversation_id = str(raw.get("id") or "").strip()
    if not conversation_id:
        return None

    created_at = str(raw.get("created_at") or _now_iso_timestamp())
    updated_at = str(raw.get("updated_at") or created_at)
    title = str(raw.get("title") or "").strip() or f"Conversation {conversation_id[:8]}"

    messages = []
    for msg in raw.get("messages", []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = str(msg.get("text") or "").strip()
        if not text:
            continue
        messages.append({
            "role": role,
            "text": text,
            "source": str(msg.get("source") or ""),
            "timestamp": str(msg.get("timestamp") or ""),
        })

    return {
        "id": conversation_id,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": messages,
    }

def _load_conversation_store():
    path = _conversation_store_path()
    if not path.exists():
        return _empty_conversation_store()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log(f"Could not read conversations file: {exc}")
        return _empty_conversation_store()

    if not isinstance(payload, dict):
        return _empty_conversation_store()

    normalized = []
    for raw in payload.get("conversations", []):
        conversation = _normalize_conversation(raw)
        if conversation:
            normalized.append(conversation)

    return {
        "version": 1,
        "conversations": normalized,
    }

def _save_conversation_store(store):
    path = _conversation_store_path()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "version": 1,
        "conversations": store.get("conversations", []),
    }

    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(path)
        return True
    except Exception as exc:
        _log(f"Could not save conversations file: {exc}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False

def _sorted_conversations(store):
    conversations = list(store.get("conversations", []))
    conversations.sort(
        key=lambda c: (str(c.get("updated_at") or ""), str(c.get("created_at") or "")),
        reverse=True,
    )
    return conversations

def _find_conversation(store, conversation_id):
    target = str(conversation_id or "").strip()
    if not target:
        return None
    for conversation in store.get("conversations", []):
        if conversation.get("id") == target:
            return conversation
    return None

def _set_active_conversation(scene, conversation_id):
    try:
        scene.suzanne_va_active_conversation = str(conversation_id or _NO_CONVERSATION_ID)
    except Exception:
        pass

def _sync_active_conversation(scene, store):
    active_id = str(getattr(scene, "suzanne_va_active_conversation", "") or "").strip()
    if active_id and active_id != _NO_CONVERSATION_ID and _find_conversation(store, active_id):
        return active_id
    if active_id == _NO_CONVERSATION_ID:
        return _NO_CONVERSATION_ID

    conversations = _sorted_conversations(store)
    if conversations:
        selected = conversations[0].get("id", _NO_CONVERSATION_ID)
        _set_active_conversation(scene, selected)
        return selected

    _set_active_conversation(scene, _NO_CONVERSATION_ID)
    return _NO_CONVERSATION_ID

def _get_active_conversation(scene, create_if_missing=False, title_seed=""):
    store = _load_conversation_store()
    active_id = _sync_active_conversation(scene, store)
    conversation = None if active_id == _NO_CONVERSATION_ID else _find_conversation(store, active_id)

    if conversation or not create_if_missing:
        return conversation, store

    now = _now_iso_timestamp()
    conversation = {
        "id": uuid.uuid4().hex,
        "title": _conversation_title_from_seed(title_seed),
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    store.setdefault("conversations", []).append(conversation)
    if _save_conversation_store(store):
        _set_active_conversation(scene, conversation["id"])
    return conversation, store

def _conversation_enum_items(self, context):
    store = _load_conversation_store()
    conversations = _sorted_conversations(store)

    items = [(
        _NO_CONVERSATION_ID,
        "No conversation",
        "Do not attach prior local conversation messages.",
    )]
    for conversation in conversations:
        conv_id = str(conversation.get("id") or "").strip()
        if not conv_id:
            continue
        title = _clip_text(conversation.get("title", "Untitled"), 42)
        message_count = len(conversation.get("messages", []))
        updated_at = conversation.get("updated_at", "")
        description = f"{message_count} message(s)"
        if updated_at:
            description = f"Updated {updated_at} | {description}"
        items.append((conv_id, title, description))

    return _set_enum_items_cache(_CONVERSATION_ENUM_ITEMS_CACHE, items)

def _conversation_context_block(scene):
    if not getattr(scene, "suzanne_va_use_conversation_context", False):
        return ""

    conversation, _ = _get_active_conversation(scene, create_if_missing=False)
    if not conversation:
        return ""

    max_turns = max(1, int(getattr(scene, "suzanne_va_context_turns", 4)))
    max_messages = max_turns * 2
    recent_messages = conversation.get("messages", [])[-max_messages:]

    lines = []
    for msg in recent_messages:
        role = "User" if msg.get("role") == "user" else "Assistant"
        text = _clip_text(msg.get("text", ""), _CONVERSATION_MESSAGE_CHAR_LIMIT)
        if not text:
            continue
        lines.append(f"{role}: {text}")

    if not lines:
        return ""
    joined_lines = "\n".join(lines)

    return (
        "## Previous Conversation Context\n"
        "```text\n"
        f"{joined_lines}\n"
        "```"
    )

def _append_conversation_exchange(scene, user_text, assistant_text, source):
    prefs = _get_addon_preferences()
    if prefs and not getattr(prefs, "auto_save_conversations", True):
        return True

    conversation, store = _get_active_conversation(
        scene,
        create_if_missing=True,
        title_seed=user_text,
    )
    if not conversation:
        return False

    now = _now_iso_timestamp()
    messages = conversation.setdefault("messages", [])

    user_clean = str(user_text or "").strip()
    assistant_clean = str(assistant_text or "").strip()
    if user_clean:
        messages.append({
            "role": "user",
            "text": user_clean,
            "source": source,
            "timestamp": now,
        })
    if assistant_clean:
        messages.append({
            "role": "assistant",
            "text": assistant_clean,
            "source": "assistant",
            "timestamp": now,
        })

    if len(messages) > 400:
        conversation["messages"] = messages[-400:]
    conversation["updated_at"] = now
    conversation["title"] = str(conversation.get("title") or "").strip() or _conversation_title_from_seed(user_clean)

    return _save_conversation_store(store)

def _new_conversation(scene, title_seed=""):
    store = _load_conversation_store()
    now = _now_iso_timestamp()
    conversation = {
        "id": uuid.uuid4().hex,
        "title": _conversation_title_from_seed(title_seed),
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    store.setdefault("conversations", []).append(conversation)
    if not _save_conversation_store(store):
        return None
    _set_active_conversation(scene, conversation["id"])
    return conversation

def _rename_conversation(scene, new_title):
    store = _load_conversation_store()
    active_id = str(getattr(scene, "suzanne_va_active_conversation", "") or "").strip()
    if not active_id or active_id == _NO_CONVERSATION_ID:
        return False

    conversation = _find_conversation(store, active_id)
    if not conversation:
        return False

    cleaned_title = str(new_title or "").strip()
    if not cleaned_title:
        return False

    conversation["title"] = _clip_text(cleaned_title, 72)
    conversation["updated_at"] = _now_iso_timestamp()
    return _save_conversation_store(store)

def _delete_active_conversation(scene):
    store = _load_conversation_store()
    active_id = str(getattr(scene, "suzanne_va_active_conversation", "") or "").strip()
    if not active_id or active_id == _NO_CONVERSATION_ID:
        return False

    before = len(store.get("conversations", []))
    store["conversations"] = [
        c for c in store.get("conversations", [])
        if c.get("id") != active_id
    ]
    if len(store["conversations"]) == before:
        return False

    if not _save_conversation_store(store):
        return False

    _sync_active_conversation(scene, store)
    return True

def _conversation_preview_lines(scene, max_items=8):
    conversation, _ = _get_active_conversation(scene, create_if_missing=False)
    if not conversation:
        return []

    messages = conversation.get("messages", [])
    if not messages:
        return []

    preview = []
    for msg in messages[-max(1, max_items):]:
        role = "You" if msg.get("role") == "user" else "Suzanne"
        body = _clip_text(_clean_markdown(msg.get("text", "")).replace("\n", " "), 140)
        if body:
            preview.append(f"{role}: {body}")
    return preview

def _log(msg):
    print(f"[Suzanne VA] {msg}")

def _build_openai_headers(api_key):
    api_key = (api_key or "").strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Suzanne-VA-Addon/1.7.0",
    }
    return headers

def _post_multipart(url, api_key, fields, files):
    boundary = f"----suzanne-va-{uuid.uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    for name, file_info in files.items():
        filename, content_type, data = file_info
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(data)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())

    req = Request(url, data=body, method="POST")
    for key, value in _build_openai_headers(api_key).items():
        req.add_header(key, value)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    with urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")

def _post_json(url, api_key, payload):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    for key, value in _build_openai_headers(api_key).items():
        req.add_header(key, value)
    req.add_header("Content-Type", "application/json")

    with urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")

def _get_json(url, api_key):
    req = Request(url, method="GET")
    for key, value in _build_openai_headers(api_key).items():
        req.add_header(key, value)

    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")

def _read_http_error_body(exc):
    try:
        body = exc.read()
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body)
    except Exception:
        return ""

def _read_file_bytes(path):
    with open(path, "rb") as f:
        return f.read()

def _transcribe_audio(api_key, model, audio_path):
    mime_type, _ = mimetypes.guess_type(audio_path)
    if not mime_type:
        mime_type = "audio/wav"

    fields = {
        "model": model,
    }
    files = {
        "file": (os.path.basename(audio_path), mime_type, _read_file_bytes(audio_path)),
    }
    response_text = _post_multipart(
        "https://api.openai.com/v1/audio/transcriptions",
        api_key,
        fields,
        files,
    )
    return json.loads(response_text)

def _call_chatgpt(api_key, model, input_text):
    payload = {
        "model": model,
        "input": input_text,
    }
    response_text = _post_json(
        "https://api.openai.com/v1/responses",
        api_key,
        payload,
    )
    return json.loads(response_text)

# Export all helper symbols (including underscore-prefixed) for split modules.
__all__ = [name for name in globals() if not name.startswith("__")]
