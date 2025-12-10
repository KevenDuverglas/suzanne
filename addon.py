bl_info = {
    "name": "Suzanne Assistant ",
    "author": "Keven Michel Duverglas",
    "version": (1,7, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Suzanne",
    "description": "Chat with OpenAI and transcribe audio files.",
    "category": "3D View",
}

import bpy, os
from bpy.types import Operator, Panel
from bpy.props import StringProperty, EnumProperty
from openai import OpenAI

# ----------------------------- utils -----------------------------
def _tag_redraw_all():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()

def _friendly_error(e: Exception) -> str:
    msg = str(e)
    if "insufficient_quota" in msg or "code: 429" in msg:
        return ("⚠️ OpenAI: insufficient quota (429). "
                "Add a payment method/credits for this project or raise the spend limit.")
    if "401" in msg or "invalid_api_key" in msg:
        return "🔑 API key error (401). Check the key and selected project."
    if "timed out" in msg or "Timeout" in msg:
        return "⌛ Network timeout. Try again."
    return f"❌ Error: {msg}"

def _resolve(path: str) -> str:
    return bpy.path.abspath(path).strip() if path else ""

# ------------------------- scene properties ----------------------
def ensure_props():
    sc = bpy.types.Scene

    if not hasattr(sc, "suzanne_prompt"):
        sc.suzanne_prompt = StringProperty(
            name="Prompt",
            description="Ask Suzanne anything about Blender",
            default="",
        )
    if not hasattr(sc, "suzanne_reply"):
        sc.suzanne_reply = StringProperty(
            name="Reply",
            description="Suzanne's response text",
            default="",
        )
    if not hasattr(sc, "suzanne_api_key"):
        sc.suzanne_api_key = StringProperty(
            name="OpenAI API Key",
            description="Paste your OpenAI key here (local to this .blend)",
            default="",
        )
    if not hasattr(sc, "suzanne_model"):
        sc.suzanne_model = StringProperty(
            name="Chat Model",
            description="e.g., gpt-4o-mini, gpt-4o",
            default="gpt-4o-mini",
        )

    # ---- Transcription (file only) ----
    if not hasattr(sc, "suzanne_audio_path"):
        sc.suzanne_audio_path = StringProperty(
            name="Audio File",
            description="Pick an audio file to transcribe (wav/mp3/m4a/webm)",
            default="",
            subtype='FILE_PATH'
        )
    if not hasattr(sc, "suzanne_transcribe_model"):
        sc.suzanne_transcribe_model = EnumProperty(
            name="Transcribe Model",
            description="Model used for speech-to-text",
            items=[
                ("gpt-4o-mini-transcribe", "gpt-4o-mini-transcribe", ""),
                ("whisper-1", "whisper-1", ""),
            ],
            default="gpt-4o-mini-transcribe",
        )

# ----------------------------- chat ------------------------------
class SUZANNE_OT_SendToOpenAI(Operator):
    bl_idname = "suzanne.send_to_openai"
    bl_label = "Send to OpenAI"

    def execute(self, context):
        sc = context.scene
        prompt = sc.suzanne_prompt.strip()
        if not prompt:
            sc.suzanne_reply = "Please type a prompt first."
            _tag_redraw_all(); return {'FINISHED'}

        api_key = sc.suzanne_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            sc.suzanne_reply = "⚠️ No API key provided. Paste it below."
            _tag_redraw_all(); return {'FINISHED'}

        sc.suzanne_reply = "⏳ Thinking…"; _tag_redraw_all()
        client = OpenAI(api_key=api_key)

        try:
            r = client.chat.completions.create(
                model=sc.suzanne_model,
                messages=[
                    {"role":"system","content":"You are Suzanne, a friendly Blender assistant. Answer clearly with short, step-by-step instructions when helpful."},
                    {"role":"user","content":prompt},
                ],
                temperature=0.7, max_tokens=400,
            )
            text = (r.choices[0].message.content or "").strip()
            sc.suzanne_reply = text or "I didn't receive any text back from the model."
        except Exception as e:
            sc.suzanne_reply = _friendly_error(e)

        _tag_redraw_all()
        return {'FINISHED'}

# --------------------------- transcribe (file) -------------------
class SUZANNE_OT_TranscribeAudio(Operator):
    """Transcribe an audio file; also asks Suzanne and returns the answer."""
    bl_idname = "suzanne.transcribe_audio"
    bl_label = "Transcribe Audio → Prompt + Answer"

    def execute(self, context):
        sc = context.scene
        path = _resolve(sc.suzanne_audio_path)
        if not path or not os.path.isfile(path):
            sc.suzanne_reply = "⚠️ Pick a valid audio file first."
            _tag_redraw_all(); return {'CANCELLED'}

        api_key = sc.suzanne_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            sc.suzanne_reply = "⚠️ No API key provided. Paste it below."
            _tag_redraw_all(); return {'CANCELLED'}

        sc.suzanne_reply = "⏳ Transcribing audio…"; _tag_redraw_all()
        client = OpenAI(api_key=api_key, timeout=60.0)

        try:
            # 1) Transcribe
            with open(path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model=sc.suzanne_transcribe_model,
                    file=f,
                )
            transcript = (getattr(result, "text", "") or "").strip()
            if not transcript:
                sc.suzanne_reply = "😕 Transcription returned no text."
                _tag_redraw_all(); return {'FINISHED'}

            # Put transcript into the Prompt field
            sc.suzanne_prompt = transcript
            _tag_redraw_all()

            # 2) Ask Suzanne using the transcript
            sc.suzanne_reply = "⏳ Asking Suzanne…"; _tag_redraw_all()
            r = client.chat.completions.create(
                model=sc.suzanne_model,
                messages=[
                    {"role":"system","content":"You are Suzanne, a friendly Blender assistant. Answer clearly with short, step-by-step instructions when helpful."},
                    {"role":"user","content": transcript},
                ],
                temperature=0.7, max_tokens=500,
            )
            answer = (r.choices[0].message.content or "").strip()

            # 3) Show both transcript and the answer
            preview = (transcript[:300] + "…") if len(transcript) > 300 else transcript
            sc.suzanne_reply = f"📝 Transcribed:\n{preview}\n\n🤖 Answer:\n{answer or '(no text)'}"

        except Exception as e:
            sc.suzanne_reply = _friendly_error(e)

        _tag_redraw_all()
        return {'FINISHED'}

# ------------------------------ UI ------------------------------
class SUZANNE_PT_Panel(Panel):
    bl_label = "Suzanne (OpenAI)"
    bl_idname = "SUZANNE_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Suzanne"

    def draw(self, context):
        sc = context.scene
        layout = self.layout

        # Chat
        layout.label(text="Prompt to Suzanne:")
        layout.prop(sc, "suzanne_prompt", text="")
        layout.operator(SUZANNE_OT_SendToOpenAI.bl_idname, icon="OUTLINER_OB_SPEAKER")

        layout.separator()
        layout.label(text="Suzanne’s Reply:")
        box = layout.box()
        for line in (sc.suzanne_reply or "").splitlines():
            box.label(text=line, icon="INFO")

        # Transcribe (file only) – now also asks Suzanne automatically
        layout.separator()
        layout.label(text="Audio → Text → Answer:")
        row = layout.row()
        row.prop(sc, "suzanne_audio_path", text="")
        layout.prop(sc, "suzanne_transcribe_model", text="Transcribe Model")
        layout.operator(SUZANNE_OT_TranscribeAudio.bl_idname, icon="SPEAKER")

        # Settings
        layout.separator()
        col = layout.column(align=True)
        col.label(text="OpenAI Settings:")
        col.prop(sc, "suzanne_api_key", text="API Key")
        col.prop(sc, "suzanne_model", text="Chat Model")

# ------------------------- registration -------------------------
classes = (
    SUZANNE_OT_SendToOpenAI,
    SUZANNE_OT_TranscribeAudio,
    SUZANNE_PT_Panel,
)

def register():
    ensure_props()
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
