#!/usr/bin/env python3
"""Rebuild mc_pools.json from the Project Gutenberg text (ebook #1184).

The pools ship with the repo, so this only matters if you want to change the
extraction. Downloads the 1846 English translation (US public domain), strips
the PG boilerplate (which is NOT part of the public-domain text), splits by
the body's chapter headings (indented one space; the TOC's are flush left),
and pools quoted speech and narration per act.
"""
import json, pathlib, re, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
URL = "https://www.gutenberg.org/cache/epub/1184/pg1184.txt"
raw = urllib.request.urlopen(URL).read().decode("utf-8")
body = raw[raw.index("\n", raw.index("*** START")) + 1:raw.index("*** END")]
parts = re.split(r"\n Chapter (\d+)\.", body)
per = {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
ACTS = {"act1": range(1, 15), "act2": range(15, 26), "act3": range(26, 40), "act4": range(40, 118)}

def extract(text):
    speech = []
    for q in re.findall(r"“([^”]{30,170})”", text):
        q = re.sub(r"\s+", " ", q.replace("\n", " ")).strip()
        if q and q[0].isupper() and q[-1] in ".!?—" and "_" not in q:
            speech.append(q)
    narration = [re.sub(r"\s+", " ", n)
                 for n in re.findall(r"(?<=\n)([A-Z][^“”\n]{60,200}[.])(?=\s)", text)]
    return speech, narration

pools = {}
for act, rng in ACTS.items():
    sp, na = [], []
    for c in rng:
        if c in per:
            s, n = extract(per[c]); sp += s; na += n
    pools[act] = {"speech": sp, "narration": na}
json.dump(pools, open(HERE / "mc_pools.json", "w"), ensure_ascii=False)
(HERE / "mc.txt").write_text(raw, encoding="utf-8")
print({a: len(p["speech"]) for a, p in pools.items()})
