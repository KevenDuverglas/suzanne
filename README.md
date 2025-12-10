# Suzanne Assistant for Blender

Suzanne Assistant is an in-viewport helper for Blender that lets you:

- 💬 Chat with OpenAI directly inside the 3D View
- 🎙️ Transcribe audio files to text
- 🔁 Automatically send that transcription to the chat model and show the answer

Everything lives in the **N-panel** in the 3D View, so you never have to leave Blender while you’re working.

---

## Features

- **Blender-native UI**
  - Panel location: `View3D > N-Panel > Suzanne`
  - Works in Blender **3.0+**

- **Chat with OpenAI**
  - Type any question in the **Prompt** field
  - Get short, clear, step-by-step answers from “Suzanne”
  - Model is configurable (e.g. `gpt-4o-mini`, `gpt-4o`)

- **Audio → Text → Answer**
  - Pick an audio file (`.wav`, `.mp3`, `.m4a`, `.webm`)
  - Transcribe using `gpt-4o-mini-transcribe` or `whisper-1`
  - The transcript is:
    - Saved into the Prompt box, and
    - Automatically sent to the chat model
  - The panel shows both the transcript (preview) and Suzanne’s answer

- **User-friendly error messages**
  - Quota / 429 errors
  - Invalid / missing API key
  - Network timeouts
  - All reported directly in the panel

- **Local API key storage**
  - API key is stored in the **.blend file only**
  - Alternatively, you can use the `OPENAI_API_KEY` environment variable

---

## Requirements

- **Blender**: 3.0 or newer  
- **Python**: Uses Blender’s bundled Python (no separate install required)  
- **Python Libraries**
  - [`openai` Python SDK (1.x)](https://pypi.org/project/openai/)
    - The add-on uses the `OpenAI` client from `openai>=1.0.0`.

`bpy`, `os`, and the other standard modules are already available inside Blender.

---

## Installing the OpenAI Python Library

Suzanne Assistant expects the `openai` package to be installed in **Blender’s Python**, not your system Python.

### Option 1 – Install from a terminal

1. Find Blender’s Python executable:
   - Open Blender → **Scripting** workspace.
   - In the Python console, run:

     ```python
     import sys
     print(sys.executable)
     ```

   - Copy that path (for example: `/path/to/blender/3.6/python/bin/python`).

2. In your system terminal, run:

   ```bash
   "<path-you-copied>" -m ensurepip --upgrade
   "<path-you-copied>" -m pip install "openai>=1.0.0,<2.0.0"
