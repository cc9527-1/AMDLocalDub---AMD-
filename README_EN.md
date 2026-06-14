# AMDLocalDub — AMD Offline Video Dubbing

> **AMD GPU accelerated · local-first · video translation & dubbing tool**

---

## What it does

Converts foreign language videos into dubbed versions. Speech recognition and video encoding run **locally on your machine**. No video data is uploaded to any cloud server.

```
Input: English video → ASR (local GPU) → Translate (API/local) → TTS (online) → Video compose (local GPU) → Output: Dubbed video
```

---

## Local vs Online

| Stage | Where it runs | Notes |
|-------|--------------|-------|
| Speech recognition | ✅ **Local only** | whisper.cpp Vulkan, model loaded locally, AMD GPU |
| Translation | ⚠️ **Optional** | SiliconFlow / DeepSeek API (needs internet) or LM Studio local model (offline) |
| TTS dubbing | 🌐 **Needs internet** | Edge-TTS, Microsoft online speech service |
| Video composition | ✅ **Local only** | ffmpeg AMF, AMD GPU hardware encoding |
| Your video | ✅ **Stays local** | Never uploaded anywhere |

> **Bottom line**: ASR and video encoding are fully local with AMD GPU. Translation can be either API (online) or LM Studio (offline). TTS currently requires internet for Edge-TTS.

---

## AMD GPU Acceleration

Optimized for **AMD Radeon RX 9070 XT** (works with any AMD GPU that supports Vulkan):

| Stage | Method | GPU |
|-------|--------|-----|
| Speech recognition | whisper.cpp **Vulkan** backend | ✅ **AMD GPU** |
| Video encoding | ffmpeg **AMF** (h264_amf) | ✅ **AMD GPU** |
| Translation | CPU (no GPU needed) | — |
| TTS dubbing | CPU (needs internet) | — |

> No CUDA / NVIDIA required. **AMD GPU users get full hardware acceleration.**

---

## Quick Start

```bash
# Windows: double-click
start_amdlocaldub.bat

# Or packaged release:
# Unzip → double-click AMDLocalDub.exe or start.bat

# Open browser
http://127.0.0.1:7860
```

### Usage

1. Enter a local video path (recommended) or drag & drop a file
2. Select translation engine
3. Click "Start" — the pipeline runs automatically

---

## Features

- **Speech recognition**: whisper.cpp + Vulkan GPU, 99 languages, fully local
- **Translation engines**: SiliconFlow / LM Studio (local) / DeepSeek API — switchable
- **Smart splitting**: sentence-boundary segmentation, merge shorts, split longs
- **TTS dubbing**: Edge-TTS (online), 23 languages, 50+ voices
- **Video composition**: AMD AMF GPU encoding, hardcoded subtitles (white on black)
- **Audio alignment**: auto-stretch TTS audio to match subtitle timestamps
- **Batch processing**: queue multiple files, process sequentially

---

## Output

```
output_dir/
├── video_name_dubbed.mp4     ← Final video
├── video_name_dubbed.srt     ← Subtitle file
└── .video_name_dubbed_cache/ ← Temp files (safe to delete)
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| UI | Gradio 6.x |
| ASR | whisper.cpp (Vulkan, local) |
| Translation | OpenAI-compatible API (local models supported) |
| TTS | Edge-TTS (online) |
| Audio/Video | ffmpeg + AMF GPU encoding (local) |
| Language | Python 3.14 |
