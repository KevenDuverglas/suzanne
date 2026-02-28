# Suzanne Voice Assistant (Blender Add-on)

Suzanne Voice Assistant is a Blender sidebar add-on for Blender-focused text and voice help.

Current version: `1.8.2`  
Blender target: `5.0.0+`  
Panel location: `3D Viewport > N-Panel > Suzanne`

## What It Does

- Sends typed prompts to OpenAI from inside Blender.
- Records voice with one microphone toggle button (start/stop on press).
- Transcribes audio and sends the transcript to the chat model automatically.
- Optionally attaches the last 100 lines of Blender Info history.
- Stores local conversation history and can include recent turns as context.
- Keeps responses Blender-only by design.

## Main UI Sections

- `Status`: current state (`Idle`, `Recording`, `Sending`, error states).
- `Ask`: text prompt input + send button.
- `Voice`: one `Microphone` button to toggle recording ON/OFF.
- `Context`:
  - `Use Conversation Context`
  - `Context Turns`
  - `Include Info History (100 lines)`
- `Conversation`: select/create/rename/delete local conversations.
- `Latest Output`: switch between transcript and response previews.

## Requirements

- Blender `5.0.0` or newer.
- Internet connection.
- Valid OpenAI API key.
- Recording backend:
  - Linux/Windows: `ffmpeg` available on `PATH`.
  - macOS: bundled `atunc` binary in `suzanne/atunc/atunc` (if missing, voice recording will fail).

No external Python package install is required for this version. The add-on uses standard library HTTP calls (`urllib`) and Blender APIs.

## Install

### Option 1: Install from GitHub ZIP (recommended)

1. Open the GitHub repository page for this add-on.
2. Click `Code > Download ZIP`.
3. In Blender, go to `Edit > Preferences > Add-ons > Install...`
4. Select the downloaded GitHub ZIP file (do not unzip it first).
5. Enable `Suzanne Voice Assistant`.

Expected structure in the downloaded ZIP:

```text
<repo-name>-main/
  __init__.py
  common.py
  operators.py
  panel.py
  preferences.py
  state.py
```

### Option 2: Install from folder (development)

1. Copy the `suzanne` folder into Blender add-ons directory:
   - Linux: `~/.config/blender/<version>/scripts/addons/`
   - Windows: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/<version>/scripts/addons/`
2. Restart Blender.
3. Enable `Suzanne Voice Assistant` in Add-ons.

## First-Time Setup

1. Open add-on preferences.
2. Confirm the compatibility note shows `Compatible with Blender 5.0.0 and newer`.
3. Paste your OpenAI API key.
4. Choose:
   - `ChatGPT Model` (default usually `gpt-4o-mini`)
   - `Transcription Model` (default usually `gpt-4o-mini-transcribe`)
5. Run diagnostics buttons:
   - `Test API Key`
   - `Test Microphone`
   - `Test Transcription`

## Daily Usage

### Text workflow

1. Type question in `Ask`.
2. Optional: enable `Include Info History (100 lines)` in `Context`.
3. Click `Send Message`.

### Voice workflow

1. Click `Microphone` to start recording.
2. Click again to stop recording.
3. Add-on transcribes audio and sends it automatically.
4. Read result under `Latest Output`.

## Local Data Storage

Conversation file:

- Primary location: `<addon_folder>/data/suzanne_conversations.json`
- Fallback location if add-on folder is not writable: `/tmp/suzanne_va_data/suzanne_conversations.json` (platform temp dir)

Recordings folder:

- Primary location: `<addon_folder>/recordings`
- Fallback location if add-on folder is not writable: platform temp dir `suzanne_va_recordings`

## Troubleshooting

### "Missing OpenAI API key"

- Add your key in add-on preferences.
- Use `Test API Key` to verify.

### Microphone test fails on Linux/Windows

- Confirm `ffmpeg` is installed and available on PATH:
  - `ffmpeg -version`
- Restart Blender after installing.

### Microphone fails on macOS

- Confirm `suzanne/atunc/atunc` exists and is executable.

### No useful transcript returned

- Try a different transcription model.
- Check mic input level and recording permissions.
- Keep recordings a little longer before stopping.

### Conversation history does not persist

- Check filesystem write permissions to add-on folder.
- Look in fallback temp path if needed.

## Privacy Notes

- Prompts, transcripts, and attached context are sent to OpenAI API when you send requests.
- Conversation history and recordings are stored locally on your machine.
