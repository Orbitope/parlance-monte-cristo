#!/usr/bin/env python3
"""Geography and content reachability — the check routes cannot perform.

Route entities walk DIALOGUE graphs. They cannot tell you whether the player
can physically get to the room a dialogue lives in, so a missing exit passes
every other check in the toolchain: schemas validate, references resolve,
routes pass, and a third of the game is simply unvisitable.

That happened three times while authoring this project (no return to
Marseilles after Act III, Rome one-way from Paris, the finale gated behind
the mercy it was supposed to decide) and each was found by a random walker
getting stuck, which is a slow and unreliable oracle.

Two passes:
  LOCATIONS — every location reachable from the start, ignoring gates. Gates
              are flag/item conditions the player can satisfy; a missing EXIT
              is unsatisfiable, and that is the bug class this catches.
  DIALOGUES — every dialogue referenced by something that can present it: a
              location interactable, a character ladder, a cutscene chain, an
              exit's denialDialogue, or a set_active_dialogue route.

Exit code 1 on any finding.
"""
import json, pathlib, sys, glob

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)

def load(sub):
    out = {}
    for f in glob.glob(str(ROOT / "data" / sub / "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        out[d["id"]] = d
    return out

locations, characters = load("locations"), load("characters")
dialogues, cutscenes = load("dialogues"), load("cutscenes")
problems = []

# --- locations ------------------------------------------------------------
start = next((l for l in locations.values() if "start" in l.get("tags", [])), None)
if start is None:
    problems.append("no location tagged 'start'")
else:
    seen, queue = {start["id"]}, [start["id"]]
    while queue:
        cur = locations[queue.pop()]
        for ex in cur.get("exits", []):
            nxt = ex["to"]["location"]
            if nxt not in locations:
                problems.append(f"{cur['id']}: exit to unknown location '{nxt}'")
            elif nxt not in seen:
                seen.add(nxt); queue.append(nxt)
    for lid in sorted(set(locations) - seen):
        problems.append(f"location '{lid}' is UNREACHABLE from '{start['id']}'")
    # A TRAP is a room you can enter and never leave — measured over the whole
    # graph, not by direct reverse edges. One-way transitions are normal here
    # (you do not walk out of the Château d'If back to the courthouse); what
    # must never happen is a room from which the start is unreachable, because
    # that strands every location behind it.
    def reaches(src, dst):
        seen, queue = {src}, [src]
        while queue:
            for e in locations[queue.pop()].get("exits", []):
                n = e["to"]["location"]
                if n == dst: return True
                if n in locations and n not in seen:
                    seen.add(n); queue.append(n)
        return False
    for lid in sorted(seen):
        if lid != start["id"] and not reaches(lid, start["id"]):
            problems.append(f"TRAP: '{lid}' cannot reach the start location — "
                            f"everything past it is stranded once entered")

# --- dialogues ------------------------------------------------------------
presented = set()
for loc in locations.values():
    for it in loc.get("interactables", []):
        if it["kind"] == "object":
            presented.add(it["dialogue"])
    for ex in loc.get("exits", []):
        if ex.get("denialDialogue"):
            presented.add(ex["denialDialogue"])
for ch in characters.values():
    for rung in ch.get("dialogues", []):
        presented.add(rung["dialogue"])
for cs in cutscenes.values():
    if cs.get("entersDialogue"):
        presented.add(cs["entersDialogue"])
for d in dialogues.values():
    for n in d["nodes"]:
        effs = list(n.get("onEnter", []))
        for c in n.get("choices", []):
            effs += c.get("effects", [])
        for e in effs:
            if e["type"] == "set_active_dialogue":
                presented.add(e["dialogue"])
for did in sorted(set(dialogues) - presented):
    problems.append(f"dialogue '{did}' is never presented by anything")

if problems:
    print(f"REACHABILITY: {len(problems)} problem(s)")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print(f"REACHABILITY OK — {len(locations)} locations all reachable, "
      f"{len(dialogues)} dialogues all presented")
