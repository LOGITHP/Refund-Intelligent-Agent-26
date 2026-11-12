# Agentic Refund Intelligence & Resolution Platform — Explainer Video Studio

Interactive 16:9 (`1920×1080`, 30 fps) screen-recordable presentation player built with React and `@remotion/player` for **LOGITH P**.

## Quick Start

```bash
npm install
npm run dev
```

Open the local studio URL printed in your terminal to launch the **Agentic Refund Intelligence Studio** player.

## Screen Recording Guide

1. **Choose your narration pace** in the transport bar:
   - `0.9x (1m 40s)` — Relaxed Narration
   - `1.0x (1m 30s)` — Standard Presentation
   - `1.15x (1m 18s • 1.3m)` — Fast Pitch
2. **Press `F`** (or click **Fullscreen Record Mode (F)**) to expand the 16:9 canvas edge-to-edge.
3. **Start your screen recorder** (OBS, Windows Snipping Tool / Game Bar, or QuickTime).
   - While playing in Record Mode, the minimal floating HUD automatically hides after **2 seconds** of mouse inactivity so zero UI chrome obscures the video.
   - Move the mouse or press `Space` to pause and reveal the HUD again.
4. **Use the Teleprompter panel** beside the player when rehearsing or reading live voiceover; click any of the 17 narration lines to jump straight to that cue.

## Keyboard Shortcuts

| Key | Action |
| --- | --- |
| `F` | Toggle Fullscreen Record Mode (auto-hiding HUD) |
| `Space` | Play / Pause |
| `R` | Restart from Frame 0 and play |
| `C` | Toggle burned-in subtitles ON / OFF |
| `←` / `→` | Seek backward / forward by 3 seconds |
| `Esc` | Exit Record Mode |

## Optional Direct MP4 Export

If you ever want to render a standalone MP4 file directly from Remotion:

```bash
npx remotion render src/remotion/index.ts ExplainerVideo out/explainer.mp4
```
