---
name: clip
description: Turn a recorded stream VOD (plus optional chat log) into vertical Shorts/TikTok/Reels clips, with facecam on top, gameplay below, word-by-word captions, a hook line and a sound effect. Use when the user uploads a stream or long video and wants clips.
---

# Clip a stream

Needs: ffmpeg, `pip install faster-whisper` (first run downloads the `base.en` model).

1. **Find moments.** `python3 .claude/skills/clip/clip.py find VIDEO [--chat CHAT.txt] [--top 10]`
   - With chat: 10-second buckets where chat runs at least 2x its recent median. Without chat: loudness spikes (weaker).
   - Chat format: one message per line, `[H:MM:SS] user: msg` or `SECONDS msg`. Convert JSON exports to this first.
   - Each candidate has `at` (seconds), `score`, `mood` (funny/dramatic/none) and sample chat.
2. **Find the boxes.** Grab one frame (`ffmpeg -ss 60 -i VIDEO -frames:v 1 frame.png`), look at it, and pick `X,Y,W,H` for the facecam and for the gameplay (leave the facecam out of the game box). Ask the user if you aren't sure.
3. **Review before rendering.** Watch frames around each `at`. Skip moments that need context, and keep ones a stranger gets in one second. Write a one-line hook that tells a stranger what's about to happen.
4. **Render.** `python3 .claude/skills/clip/clip.py make VIDEO --at SEC --cam X,Y,W,H --game X,Y,W,H --hook "..." --sfx funny|dramatic|none -o clipN.mp4`
   - The clip runs from 25s before `at` to 5s after it. The sound effect hits 3s before `at`, because chat reacts late.
5. Check a contact sheet of every clip before handing it over. Only clip creators who allow it.
