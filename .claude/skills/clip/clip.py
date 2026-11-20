#!/usr/bin/env python3
"""Find hype moments in a stream VOD and render vertical cam-over-game clips.

  clip.py find VIDEO [--chat CHAT] [--top N]        -> JSON candidates on stdout
  clip.py make VIDEO --at SEC --cam X,Y,W,H --game X,Y,W,H [--hook TEXT] [--sfx funny|dramatic|none] -o OUT.mp4
"""
import argparse, json, os, re, statistics, subprocess, sys, tempfile

BEFORE, AFTER, BUCKET = 25, 5, 10
FUNNY = ("lol", "lmao", "lmfao", "haha", "kekw", "omegalul", "😂", "🤣", "💀")
DRAMA = ("no way", "omg", "wtf", "holy", "bro what", "ayo", "😱", "😳", "nooo", "w stream", "clip")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet CDN is blocked behind some proxies

def sh(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout

def duration(video):
    return float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video))

# shortcut: plain-text chat only ("[H:MM:SS] user: msg" or "SECONDS msg" per line); convert JSON exports first.
TS = re.compile(r"^\[?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]?\s+(.*)|^(\d+(?:\.\d+)?)\s+(.*)")

def read_chat(path):
    msgs = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = TS.match(line.strip())
        if not m:
            continue
        if m.group(5):
            msgs.append((float(m.group(5)), m.group(6)))
        else:
            h, mi, s = int(m.group(1) or 0), int(m.group(2)), float(m.group(3))
            msgs.append((h * 3600 + mi * 60 + s, m.group(4)))
    return msgs

def mood(texts):
    t = " ".join(texts).lower()
    f, d = sum(t.count(k) for k in FUNNY), sum(t.count(k) for k in DRAMA)
    return "funny" if f > d else "dramatic" if d else "none"

def chat_spikes(msgs, length):
    """Buckets where chat runs >= 2x its recent median (and >= 5 msgs)."""
    n = int(length // BUCKET) + 1
    counts, texts = [0] * n, [[] for _ in range(n)]
    for t, msg in msgs:
        if 0 <= t < length:
            counts[int(t // BUCKET)] += 1
            texts[int(t // BUCKET)].append(msg)
    out = []
    for i, c in enumerate(counts):
        base = max(1.0, statistics.median(counts[max(0, i - 30):i] or [1]))
        if c >= 5 and c >= 2 * base:
            out.append({"at": i * BUCKET + BUCKET / 2, "score": round(c / base, 2), "mood": mood(texts[i]),
                        "chat": texts[i][:8]})
    return out

def audio_spikes(video):
    """No chat: seconds whose loudness is > mean + 2.5 sd."""
    raw = sh("ffmpeg", "-v", "error", "-i", video, "-vn", "-af",
             "asetnsamples=n=48000,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
             "-ar", "48000", "-f", "null", "-")
    lv = [float(x) for x in re.findall(r"RMS_level=(-?[\d.]+|-inf)", raw.replace("-inf", "-120"))]
    if len(lv) < 2:
        return []
    mu, sd = statistics.mean(lv), statistics.pstdev(lv) or 1
    return [{"at": i + 0.5, "score": round((v - mu) / sd, 2), "mood": "none", "chat": []}
            for i, v in enumerate(lv) if v > mu + 2.5 * sd]

def pick(spikes, top):
    """Best spikes at least one clip-length apart."""
    chosen = []
    for s in sorted(spikes, key=lambda s: -s["score"]):
        if all(abs(s["at"] - c["at"]) > BEFORE + AFTER for c in chosen):
            chosen.append(s)
    return sorted(chosen[:top], key=lambda s: s["at"])

def words(video, start, end):
    import numpy as np
    from faster_whisper import WhisperModel
    # decode with ffmpeg, not PyAV: avoids PyAV version clashes
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-to", str(end), "-i", video, "-vn",
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], check=True, capture_output=True).stdout
    segs, _ = WhisperModel("base.en", compute_type="int8").transcribe(np.frombuffer(pcm, np.float32), word_timestamps=True)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in s.words]

def ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

def ass(path, ws, hook, length):
    esc = lambda s: s.replace("\\", "").replace("{", "(").replace("}", ")")
    nxt = [w[0] for w in ws[1:]] + [length]
    # end each word when the next starts, so two words never stack on screen
    ev = [f"Dialogue: 0,{ass_time(a)},{ass_time(max(min(b + 0.3, n), a + 0.1))},Word,,0,0,0,,{esc(w).upper()}"
          for (a, b, w), n in zip(ws, nxt)]
    if hook:
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(length)},Hook,,0,0,0,,{esc(hook)}")
    open(path, "w", encoding="utf-8").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,DejaVu Sans,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,8,3,5,40,40,0,1
Style: Hook,DejaVu Sans,64,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,18,0,8,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev) + "\n")

SFX = {  # synthesized so no sound files are needed
    "funny": "sin(2*PI*(320+220*sin(2*PI*9*t))*t)*exp(-2.5*t)*0.4",   # boing
    "dramatic": "(sin(2*PI*(70-35*t)*t)+0.3*random(0)*exp(-6*t))*exp(-2*t)*0.5",  # boom
}

def make(a):
    length = duration(a.video)
    start, end = max(0.0, a.at - BEFORE), min(length, a.at + AFTER)
    cx, cy, cw, ch = a.cam
    gx, gy, gw, gh = a.game
    with tempfile.TemporaryDirectory() as d:
        sub = os.path.join(d, "s.ass")
        ass(sub, words(a.video, start, end), a.hook, end - start)
        v = (f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale=1080:768:force_original_aspect_ratio=increase,crop=1080:768[c];"
             f"[0:v]crop={gw}:{gh}:{gx}:{gy},scale=1080:1152:force_original_aspect_ratio=increase,crop=1080:1152[g];"
             f"[c][g]vstack,subtitles={sub}[v]")
        inputs, au = [], "[0:a]anull[a]"
        if a.sfx in SFX:
            hit = max(0.0, a.at - start - 3)  # chat reacts ~3s after the moment
            inputs = ["-f", "lavfi", "-i", f"aevalsrc='{SFX[a.sfx]}':d=1.5:s=48000"]
            au = (f"[1:a]adelay={int(hit * 1000)}:all=1[x];"
                  "[0:a]aresample=48000[m];[m][x]amix=inputs=2:duration=first:normalize=0[a]")
        sh("ffmpeg", "-v", "error", "-y", "-ss", str(start), "-to", str(end), "-i", a.video, *inputs,
           "-filter_complex", f"{v};{au}", "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", a.out)
    print(a.out)

def box(s):
    v = [int(x) for x in s.split(",")]
    if len(v) != 4 or min(v[2:]) <= 0:
        raise argparse.ArgumentTypeError("box must be X,Y,W,H")
    return v

def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("find"); f.add_argument("video"); f.add_argument("--chat"); f.add_argument("--top", type=int, default=10)
    m = sp.add_parser("make"); m.add_argument("video"); m.add_argument("--at", type=float, required=True)
    m.add_argument("--cam", type=box, required=True); m.add_argument("--game", type=box, required=True)
    m.add_argument("--hook", default=""); m.add_argument("--sfx", choices=["funny", "dramatic", "none"], default="none")
    m.add_argument("-o", "--out", required=True)
    a = p.parse_args()
    if a.cmd == "find":
        spikes = chat_spikes(read_chat(a.chat), duration(a.video)) if a.chat else audio_spikes(a.video)
        json.dump(pick(spikes, a.top), sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        make(a)

if __name__ == "__main__":
    main()
