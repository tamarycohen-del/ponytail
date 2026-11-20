import os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from clip import read_chat, chat_spikes, pick, mood

lines = [f"[0:{t // 60:02d}:{t % 60:02d}] u{t}: hi" for t in range(0, 300, 5)]  # ~2 msgs / 10s
lines += [f"[0:02:0{i}] u: LMAO 😂" for i in range(10)]                         # spike at 120-130s
lines += ["123.5 v: no way", "garbage line"]
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write("\n".join(lines))
msgs = read_chat(f.name)
assert len(msgs) == 60 + 10 + 1, len(msgs)
best = pick(chat_spikes(msgs, 300), 5)
assert [s["at"] for s in best] == [125.0], best
assert best[0]["mood"] == "funny"
assert mood(["NO WAY", "omg"]) == "dramatic" and mood(["hello"]) == "none"
print("ok")
