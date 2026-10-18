"""Fill the SCENARIOS allowlist in api/check.ts with the exact guard request bodies from the recorded demo runs
(scenarios.json order; same ids as src/components/tryit/tryitRecorded.ts). Run: python3 scripts/gen-check-scenarios.py"""
import json, hashlib, re
from pathlib import Path
D = Path("/workspace/demo"); OUT = Path(__file__).resolve().parent.parent / "api" / "check.ts"
sc = json.loads((D / "scenarios/scenarios.json").read_text())["scenarios"]
data = {}
for s in sc:
    b = (D / s["request_path"]).read_bytes()
    fb = json.loads((D / s["fallback_path"]).read_text())
    assert fb["request_md5"] == hashlib.md5(b).hexdigest(), s["id"]  # same body that produced the recorded result
    r = json.loads(b)
    data[s["id"]] = {k: r[k] for k in ("text", "url", "action", "target")}
assert not re.search(r"\d{12,19}", json.dumps(data)), "card-like digits"
src = OUT.read_text()
block = "// GEN:SCENARIOS:BEGIN\nconst SCENARIOS: Record<string, GuardRequest> = " + json.dumps(data, indent=2, ensure_ascii=False) + ";\n// GEN:SCENARIOS:END"
src = re.sub(r"// GEN:SCENARIOS:BEGIN.*?// GEN:SCENARIOS:END", lambda _: block, src, flags=re.S)
OUT.write_text(src); print(OUT, list(data))
