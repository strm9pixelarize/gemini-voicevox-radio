import re, sys
sys.path.insert(0, "/app/py/src")
from radio.voicevox import VoiceVoxClient, host_from_env

LINE_RE = re.compile(r"^(めたん|つむぎ|ずんだもん):\s*(.+)$")
IDS = {"めたん": 2, "つむぎ": 8, "ずんだもん": 3}
lines = []
for raw in open("/data/state/program_work/15/trial/gadget_program_fixed.txt", encoding="utf-8").read().splitlines():
    m = LINE_RE.match(raw.strip())
    if m:
        lines.append((m.group(1), m.group(2)))
print(f"{len(lines)} dialogue lines", flush=True)
with VoiceVoxClient(host_from_env()) as vv:
    for i, (label, text) in enumerate(lines, 1):
        print(f"try {i} {label}: {text[:40]}", flush=True)
        vv.synthesize_line(text, IDS[label])
print("all ok", flush=True)
