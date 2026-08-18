#!/usr/bin/env python3
"""The Count of Monte Cristo as a Parlance scale fixture — hand-authored skeleton.

Every quest, gate, ladder rung, and dialogue below is individually decided from
the novel; the script is a serialization vehicle, not a generator. Node text is
drawn from the 1846 English translation (US public domain), scoped to the act
the scene belongs to, so lines land near their own part of the story.

The player is Edmond Dantès. Speakers are the people talking TO him.
"""
import json, pathlib, re, shutil, sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent)
POOLS = json.load(open(HERE / "mc_pools.json", encoding="utf-8"))
RAW = (HERE / "mc.txt").read_text(encoding="utf-8") if (HERE / "mc.txt").exists() else ""
_cursor = {}

def line(act, contains=None):
    """A spoken line from the right act; `contains` pins an anchor quote."""
    pool = POOLS[act]["speech"]
    if contains:
        for q in pool:
            if contains.lower() in q.lower():
                return q
        m = re.search(r"“([^”]*%s[^”]*)”" % re.escape(contains), RAW, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1))[:300]
        raise SystemExit(f"anchor not found: {contains!r}")
    i = _cursor.get(act, 0); _cursor[act] = i + 1
    return pool[i % len(pool)]

def narr(act):
    pool = POOLS[act]["narration"]
    i = _cursor.get(act + "_n", 0); _cursor[act + "_n"] = i + 1
    return pool[i % len(pool)]

# ---- effect / condition shorthand -----------------------------------------
def F(flag, v=True):   return {"flag": flag, "type": "set_flag", "value": v}
def CNT(c, d=1):       return {"counter": c, "delta": d, "type": "adjust_counter"}
def GIVE(item):        return {"item": item, "type": "give_item"}
def REP(fac, d):       return {"delta": d, "faction": fac, "type": "adjust_reputation"}
def REL(npc, d):       return {"character": npc, "delta": d, "type": "adjust_relationship"}
def QADV(q, s):        return {"quest": q, "toStage": s, "type": "advance_quest"}
def XP(n):             return {"amount": n, "type": "grant_xp"}
def CUT(c):            return {"cutscene": c, "type": "play_cutscene"}

def f(flag, v=True):   return {"flag": flag, "type": "flag", "value": v}
def has(item, h=True): return {"has": h, "item": item, "type": "item"}
def rep(fac, op, v):   return {"faction": fac, "op": op, "type": "reputation", "value": v}
def rel(npc, op, v):   return {"character": npc, "op": op, "type": "relationship", "value": v}
def q(qid, op, stg):   return {"op": op, "quest": qid, "stage": stg, "type": "quest"}
def qo(qid, out):      return {"outcome": out, "quest": qid, "type": "questOutcome"}
def all_(*c):          return {"of": list(c), "type": "all"}
def any_(*c):          return {"of": list(c), "type": "any"}
def not_(c):           return {"of": c, "type": "not"}

# ---- registries filled as we author; self-linted at the end ----------------
FLAG_W, FLAG_R, ITEM_G, ITEM_R = {}, set(), set(), set()
DIALOGUES, FILES = {}, {}

def _scan_cond(c):
    if not isinstance(c, dict): return
    t = c.get("type")
    if t == "flag": FLAG_R.add(c["flag"])
    if t == "item": ITEM_R.add(c["item"])
    if t in ("all", "any"):
        for s in c["of"]: _scan_cond(s)
    if t == "not": _scan_cond(c["of"])

def _scan_effects(effs, where):
    for e in effs or []:
        if e["type"] == "set_flag": FLAG_W.setdefault(e["flag"], where)
        if e["type"] == "give_item": ITEM_G.add(e["item"])

# ---- node / dialogue DSL ---------------------------------------------------
def N(nid, act, speaker=None, text=None, contains=None, nxt=None, end=False,
      on_enter=None, choices=None, narration=False):
    node = {"id": nid, "text": text or (narr(act) if narration else line(act, contains))}
    if speaker: node["speakerId"] = speaker
    if nxt: node["next"] = nxt
    if end: node["isEnd"] = True
    if on_enter:
        node["onEnter"] = on_enter
        _scan_effects(on_enter, nid)
    if choices: node["choices"] = choices
    return node

def C(cid, text, goto=None, check=None, show=None, effects=None):
    ch = {"id": cid, "text": text}
    if goto: ch["goto"] = goto
    if check:
        skill, dc, ok, bad = check
        ch["check"] = {"difficulty": dc, "mode": "active",
                       "onFailure": bad, "onSuccess": ok, "skill": skill}
    if show:
        ch["showIf"] = show; _scan_cond(show)
    if effects:
        ch["effects"] = effects; _scan_effects(effects, cid)
    return ch

def D(did, title, speaker, tags, nodes, entry=None):
    # Prefix node/choice ids with the dialogue id for global uniqueness.
    for nd in nodes:
        nd["id"] = f"{did}_{nd['id']}"
        if "next" in nd: nd["next"] = f"{did}_{nd['next']}"
        for ch in nd.get("choices", []):
            ch["id"] = f"{did}_{ch['id']}"
            if "goto" in ch: ch["goto"] = f"{did}_{ch['goto']}"
            if "check" in ch:
                ch["check"]["onSuccess"] = f"{did}_{ch['check']['onSuccess']}"
                ch["check"]["onFailure"] = f"{did}_{ch['check']['onFailure']}"
    # A node whose choices are ALL gated can leave the player with nothing to
    # click if every condition fails. The editor's FLOW pass catches this; the
    # CLI validator does not. Give any such node an unconditional way out.
    _needs_out = [n for n in nodes
                  if n.get("choices") and all("showIf" in c for c in n["choices"])]
    if _needs_out:
        _esc = {"id": f"{did}_pass", "isEnd": True,
                "text": "You let the moment go by without taking it."}
        nodes.append(_esc)
        for _n in _needs_out:
            _n["choices"].append({"id": f"{_n['id']}_wait",
                                  "text": "Say nothing. Not yet.",
                                  "goto": f"{did}_pass"})

    d = {"entry": f"{did}_{entry or nodes[0]['id'].split('_')[-1]}", "id": did,
         "nodes": nodes, "tags": tags, "title": title}
    d["entry"] = nodes[0]["id"] if entry is None else f"{did}_{entry}"
    if speaker: d["speakerId"] = speaker
    DIALOGUES[did] = d
    FILES[f"data/dialogues/{did}.json"] = d
    return did

def write_all():
    # Clear ONLY the generated trees. This used to rmtree(OUT) — and since OUT
    # defaults to the repo root, running it in place deleted the repository,
    # tools and .git included. Never remove the output root itself.
    for sub in ("data", "lore", "tests"):
        target = OUT / sub
        if target.exists():
            shutil.rmtree(target)
    OUT.mkdir(parents=True, exist_ok=True)
    for rel, obj in FILES.items():
        p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                     encoding="utf-8")

# ---- the world -------------------------------------------------------------
FILES["parlance.config.json"] = {"data": "data", "lore": "lore"}

FILES["data/skills.json"] = {"skills": [
    {"cluster": "mind",   "description": "Seeing the one detail a degree out of place.", "id": "observation", "name": "Observation"},
    {"cluster": "social", "description": "Making a true thing sound better, or a false one sound true.", "id": "rhetoric", "name": "Rhetoric"},
    {"cluster": "spirit", "description": "Holding still when holding still is the harder thing.", "id": "nerve", "name": "Nerve"},
    {"cluster": "social", "description": "Knowing which of two facts to leave in the room.", "id": "discretion", "name": "Discretion"},
]}

for fid, name, summ, opp in [
    ("fac_bonapartist", "The Bonapartists", "Those who expect the Emperor back, and write letters they should not.", ["fac_royalist"]),
    ("fac_royalist", "The Royalists", "Those who prospered by his going, and intend that he stay gone.", ["fac_bonapartist"]),
    ("fac_society", "Parisian Society", "The salons, the Opera boxes, and the credit that flows from being seen.", []),
    ("fac_underworld", "The Coast and the Catacombs", "Smugglers, bandits, and men who keep their word for their own reasons.", []),
]:
    FILES[f"data/factions/{fid}.json"] = {"id": fid, "name": name, "opposes": opp,
        "reputationRange": {"max": 10, "min": -10}, "summary": summ}

FILES["data/items.json"] = {"items": [
    {"description": "Sealed at Elba, addressed to Paris. Worth exactly one man's life to carry.", "id": "item_letter_elba", "name": "The Letter from Elba"},
    {"description": "Iron, patiently shaped over three years into something that opens stone.", "id": "item_file", "name": "A Prisoner's File"},
    {"description": "Red silk. Once held a debt; later, a fortune returned the same way it left.", "id": "item_red_purse", "name": "The Red Silk Purse"},
    {"description": "Cut, cold, and exactly the size of a man's conscience.", "id": "item_diamond", "name": "The Test Diamond"},
    {"description": "The Spada fortune. After it, money stops being a number.", "id": "item_treasure", "name": "The Treasure of Monte Cristo"},
    {"description": "Depositions, dates, and a sold fortress. Yanina, written down.", "id": "item_yanina_dossier", "name": "The Yanina Dossier"},
    {"description": "A forged signal, priced at twenty-five thousand francs of gardener's peace.", "id": "item_telegraph_note", "name": "The Telegraph Instruction"},
    {"description": "A vial from a locked cabinet. Brucine, in a house with a chemist in it.", "id": "item_poison_vial", "name": "The Poison Vial"},
]}

# ============================= ACT I — MARSEILLES ===========================
# The Pharaon comes home; the plot assembles itself out of envy, debt, and
# ambition; the feast; the arrest; the letter burned; the cell.

D("dlg_pharaon_deck", "The Pharaon — what Captain Leclère left", None, ["object", "act1"], [
    N("open", "act1", narration=True, choices=[
        C("take", "Take charge of the packet, as he asked.", goto="taken",
          effects=[GIVE("item_letter_elba"), REP("fac_bonapartist", 2), F("took_letter")]),
        C("refuse", "A dying man's politics are not your cargo. Decline.", goto="refused",
          effects=[REP("fac_royalist", 1)]),
    ]),
    N("taken", "act1", contains="the island of Elba", end=True),
    N("refused", "act1", narration=True, end=True,
      on_enter=[F("took_letter", False)]),
])

D("dlg_harbour_landing", "Marseilles — the quay", None, ["object", "act1"], [
    N("open", "act1", narration=True,
      on_enter=[QADV("qst_pharaon", "stg_pha_dock"), F("came_ashore")], nxt="crowd"),
    N("crowd", "act1", contains="Dantès", end=True),
])

D("dlg_morrel_first", "M. Morrel — the owner", "npc_morrel", ["conversation", "act1"], [
    N("open", "act1", contains="captain", choices=[
        C("report", "Report the voyage plainly: the cargo, the delay, the death.", goto="pleased",
          effects=[F("met_morrel"), REL("npc_morrel", 1)]),
        C("press", "Ask for the captaincy outright.",
          check=("rhetoric", 10, "captain", "modest")),
    ]),
    N("pleased", "act1", nxt="offer"),
    N("offer", "act1", contains="captain", end=True,
      on_enter=[F("made_captain"), QADV("qst_pharaon", "stg_pha_captain")]),
    N("captain", "act1", contains="captain", end=True,
      on_enter=[F("made_captain"), F("met_morrel"), QADV("qst_pharaon", "stg_pha_captain")]),
    N("modest", "act1", end=True,
      on_enter=[F("met_morrel"), REL("npc_morrel", 1)]),
])

D("dlg_danglars_first", "Danglars — the supercargo", "npc_danglars", ["conversation", "act1"], [
    N("open", "act1", choices=[
        C("watch", "Say little. Watch what his eyes do when Morrel is mentioned.",
          check=("observation", 9, "seen", "missed"), show=f("made_captain")),
        C("civil", "Be civil about the accounts and nothing else.", goto="civil_end"),
    ]),
    N("seen", "act1", narration=True, end=True,
      on_enter=[F("noticed_danglars"), CNT("suspicion")]),
    N("missed", "act1", end=True),
    N("civil_end", "act1", end=True),
])

D("dlg_louis_father", "Louis Dantès — the little room", "npc_louis_dantes", ["conversation", "act1"], [
    N("open", "act1", contains="father", choices=[
        C("money", "Ask what became of the money you left him.",
          check=("observation", 8, "debt", "quiet")),
        C("joy", "Let the homecoming be a homecoming. Say nothing hard.", goto="tender",
          effects=[REL("npc_louis_dantes", 1)]),
    ]),
    N("debt", "act1", end=True,
      on_enter=[F("knows_father_debt"), F("greeted_father"), REL("npc_louis_dantes", 1), CNT("suspicion")]),
    N("quiet", "act1", end=True),
    N("tender", "act1", end=True, on_enter=[F("greeted_father")]),
])

D("dlg_caderousse_first", "Caderousse — over the wine", "npc_caderousse", ["conversation", "act1"], [
    N("open", "act1", choices=[
        C("debt", "Settle your father's debt to him, and watch his face while you do.",
          show=f("knows_father_debt"), check=("discretion", 9, "loose", "tight"),
          effects=[REL("npc_caderousse", 1)]),
        C("drink", "Drink with him and keep your own counsel.", goto="drunk"),
    ]),
    N("loose", "act1", contains="Danglars", end=True,
      on_enter=[F("warned_by_caderousse"), CNT("suspicion")]),
    N("tight", "act1", end=True),
    N("drunk", "act1", end=True),
])

D("dlg_mercedes_first", "Mercédès — the Catalans", "npc_mercedes", ["conversation", "act1"], [
    N("open", "act1", contains="Edmond", choices=[
        C("ask", "Ask her now, with the whole voyage still on you.", goto="yes",
          effects=[REL("npc_mercedes", 2)]),
    ]),
    N("yes", "act1", nxt="feast_set"),
    N("feast_set", "act1", narration=True, end=True,
      on_enter=[F("betrothed"), QADV("qst_betrothal", "stg_bet_feast")]),
])

D("dlg_fernand_first", "Fernand — the man in the doorway", "npc_fernand", ["conversation", "act1"], [
    N("open", "act1", choices=[
        C("read", "Offer him your hand, and read what he does with the offer.",
          check=("observation", 10, "hate", "shrug")),
        C("ignore", "He is her cousin. Leave it at that.", goto="left"),
    ]),
    N("hate", "act1", narration=True, end=True,
      on_enter=[F("noticed_fernand"), CNT("suspicion")]),
    N("shrug", "act1", end=True),
    N("left", "act1", end=True),
])

D("dlg_reserve_feast", "La Réserve — the marriage feast", None, ["object", "act1"], [
    N("open", "act1", contains="feast", nxt="soldiers"),
    N("soldiers", "act1", narration=True, nxt="seized"),
    N("seized", "act1", contains="arrest", end=True,
      on_enter=[F("arrested"), QADV("qst_arrest", "stg_arr_seized"), REL("npc_mercedes", 1)]),
])

D("dlg_villefort_interrogation", "Villefort — the deputy's chamber", "npc_villefort", ["conversation", "act1"], [
    N("open", "act1", contains="I have read the letter", choices=[
        C("truth", "Tell it exactly: Elba, the dying captain, the address you never read.",
          show=has("item_letter_elba"), check=("nerve", 11, "believed", "doubted")),
        C("deny", "Deny the letter altogether.",
          show=f("took_letter"), check=("discretion", 13, "doubted", "doubted")),
        C("innocent", "You never took the packet. Say so, and it is even true.",
          show=f("took_letter", False), goto="believed"),
    ]),
    N("believed", "act1", contains="Noirtier", nxt="burn"),
    N("doubted", "act1", narration=True, nxt="burn"),
    N("burn", "act1", contains="letter is destroyed", end=True,
      on_enter=[F("letter_burned"), F("condemned"),
                QADV("qst_arrest", "stg_arr_letter"), REP("fac_royalist", 1)]),
])

D("dlg_cell_arrival", "The Château d'If — the door closes", None, ["object", "act1"], [
    N("open", "act1", narration=True, nxt="stone"),
    N("stone", "act1", contains="Château d’If", end=True,
      on_enter=[F("in_cell"), QADV("qst_arrest", "stg_arr_cell")]),
])

# ============================= ACT II — THE CHÂTEAU D'IF ====================

D("dlg_jailer", "The jailer — soup and silence", "npc_jailer", ["conversation", "act2"], [
    N("open", "act2", choices=[
        C("priest", "Ask again for the governor. For a priest. For anyone.",
          check=("rhetoric", 12, "pity", "wall")),
        C("silent", "Take the soup. Say nothing. Days are all one now.", goto="wall"),
    ]),
    N("pity", "act2", end=True, on_enter=[CNT("years", 1)]),
    N("wall", "act2", end=True, on_enter=[CNT("years", 1)]),
])

D("dlg_scratching", "The wall — a sound that is not water", None, ["object", "act2"], [
    N("open", "act2", narration=True, choices=[
        C("listen", "Put your ear to the stone and count the intervals.",
          check=("observation", 9, "sure", "unsure")),
        C("answer", "Knock three times, and wait.", goto="sure"),
    ]),
    N("sure", "act2", end=True,
      on_enter=[F("heard_scratching"), QADV("qst_tunnel", "stg_tun_sound")]),
    N("unsure", "act2", end=True),
])

D("dlg_faria_meet", "The breach — another man's candle", None, ["object", "act2"], [
    N("open", "act2", contains="Who are you", nxt="abbe"),
    N("abbe", "act2", contains="I am the Abbé Faria", end=True,
      on_enter=[F("met_faria"), GIVE("item_file"), REL("npc_faria", 2),
                QADV("qst_tunnel", "stg_tun_meet")]),
])

D("dlg_faria_teach_1", "Faria — languages and the shape of things", "npc_faria", ["conversation", "act2"], [
    N("open", "act2", contains="learn", choices=[
        C("learn", "Give him your mornings. Then your evenings. Then the rest.", goto="year",
          effects=[F("edu_1"), QADV("qst_education", "stg_edu_tongues")]),
    ]),
    N("year", "act2", narration=True, end=True),
])

D("dlg_faria_teach_2", "Faria — sciences, and how to hold them", "npc_faria", ["conversation", "act2"], [
    N("open", "act2", choices=[
        C("learn", "Mathematics, chemistry, the manners of three courts.", goto="more",
          effects=[F("edu_2"), QADV("qst_education", "stg_edu_sciences")]),
    ]),
    N("more", "act2", end=True),
])

D("dlg_faria_deduce", "Faria — the deduction", "npc_faria", ["conversation", "act2"], [
    N("open", "act2", contains="whom the crime will profit", choices=[
        C("danglars", "Danglars wrote it. You saw the envy at the accounts.",
          show=f("noticed_danglars"), goto="named"),
        C("fernand", "Fernand posted it. You saw what your hand cost him to shake.",
          show=f("noticed_fernand"), goto="named"),
        C("blind", "You do not know. You have never known.",
          check=("observation", 12, "named", "led")),
    ]),
    N("led", "act2", narration=True, nxt="named"),
    N("named", "act2", contains="Villefort", end=True,
      on_enter=[F("knows_betrayers"), QADV("qst_education", "stg_edu_deduction")]),
])

D("dlg_faria_treasure", "Faria — the Spada secret", "npc_faria", ["conversation", "act2"], [
    N("open", "act2", contains="this paper is my treasure", choices=[
        C("believe", "He has been right about everything else. Believe him.", goto="isle",
          effects=[F("knows_treasure"), QADV("qst_treasure", "stg_tre_secret")]),
        C("humor", "Humor an old man's arithmetic of caverns and ingots.", goto="isle",
          effects=[F("knows_treasure"), QADV("qst_treasure", "stg_tre_secret"),
                   REL("npc_faria", -1)]),
    ]),
    N("isle", "act2", contains="Monte Cristo", end=True),
])

D("dlg_faria_death", "Faria — the third attack", "npc_faria", ["conversation", "act2"], [
    N("open", "act2", contains="God", nxt="gone"),
    N("gone", "act2", narration=True, end=True,
      on_enter=[F("faria_dead"), REL("npc_faria", 1), QADV("qst_escape", "stg_esc_dead")]),
])

D("dlg_shroud", "The shroud — the only door that opens", None, ["object", "act2"], [
    N("open", "act2", narration=True, choices=[
        C("swap", "Take his place in the sack, the file inside your shirt.",
          show=has("item_file"), check=("nerve", 13, "sea", "sea")),
        C("wait", "There must be another way. There is not, and you know it.", goto="open"),
    ]),
    N("sea", "act2", text="The sea is the cemetery of the Château d’If.", end=True,
      on_enter=[F("escaped"), QADV("qst_escape", "stg_esc_shroud"), CUT("cs_escape_shroud")]),
])

D("dlg_jacopo_rescue", "The Jeune-Amélie — pulled from the water", "npc_jacopo", ["conversation", "act2"], [
    N("open", "act2", contains="shipwreck", choices=[
        C("story", "A shipwrecked sailor of the Rhône. Stick to it, shaved beard and all.",
          check=("discretion", 10, "taken", "taken")),
    ]),
    N("taken", "act2", end=True,
      on_enter=[F("aboard_amelie"), REP("fac_underworld", 2),
                QADV("qst_escape", "stg_esc_amelie"), REL("npc_jacopo", 1)]),
])

# ==================== ACT III — THE ISLE, THE PRIEST, ROME ==================

D("dlg_isle_landing", "Monte Cristo — a feigned injury", None, ["object", "act3"], [
    N("open", "act3", narration=True, end=True,
      on_enter=[F("on_isle"), QADV("qst_treasure", "stg_tre_isle")]),
])

D("dlg_grotto", "The grotto — the second chamber", None, ["object", "act3"], [
    N("open", "act3", narration=True, choices=[
        C("dig", "The corner of the second opening, as the paper said.",
          show=f("knows_treasure"), check=("observation", 8, "gold", "gold")),
    ]),
    N("gold", "act3", contains="treasure", end=True,
      on_enter=[GIVE("item_treasure"), QADV("qst_treasure", "stg_tre_found")]),
])

D("dlg_jacopo_farewell", "Jacopo — the first gift", "npc_jacopo", ["conversation", "act3"], [
    N("open", "act3", choices=[
        C("give", "A ship of his own. Watch him fail to understand, then understand.",
          show=has("item_treasure"), goto="loyal", effects=[REL("npc_jacopo", 2)]),
        C("keep", "Not yet. Loyalty tested once more is loyalty proved.", goto="tested"),
    ]),
    N("loyal", "act3", end=True, on_enter=[F("jacopo_loyal")]),
    N("tested", "act3", end=True, on_enter=[F("jacopo_loyal")]),
])

D("dlg_busoni_donning", "A cassock, a tonsure, an Italian accent", None, ["object", "act3"], [
    N("open", "act3", narration=True, end=True,
      on_enter=[F("identity_busoni"), GIVE("item_diamond"),
                QADV("qst_diamond", "stg_dia_donned")]),
])

D("dlg_caderousse_diamond", "Caderousse — the inn at Pont du Gard", "npc_caderousse", ["conversation", "act3"], [
    N("open", "act3", contains="Edmond Dantès", choices=[
        C("probe", "The abbé asks: what became of the men who knew him?",
          check=("rhetoric", 10, "tale", "tale")),
    ]),
    N("tale", "act3", contains="Danglars", nxt="tale2"),
    N("tale2", "act3", contains="Fernand", nxt="judge"),
    N("judge", "act3", narration=True,
      on_enter=[F("heard_inn_tale"), QADV("qst_diamond", "stg_dia_tale")], choices=[
        C("give", "Give him the diamond. Let what he is decide what it does to him.",
          show=has("item_diamond"), goto="given", effects=[{"item": "item_diamond", "type": "take_item"},
                                 F("gave_diamond"), REL("npc_caderousse", 1)]),
        C("hold", "He confessed to cowardice, not malice. But hold the stone.", goto="held"),
    ]),
    N("given", "act3", end=True),
    N("held", "act3", end=True),
])

D("dlg_wilmore_donning", "An Englishman's coat, a drawl, a bank's name", None, ["object", "act3"], [
    N("open", "act3", narration=True, end=True,
      on_enter=[F("identity_wilmore")]),
])

D("dlg_morrel_rescue", "Morrel — the house that must not fail", "npc_morrel", ["conversation", "act3"], [
    N("open", "act3", contains="Pharaon", choices=[
        C("buy", "As agent of Thomson & French, buy every debt the house owes.",
          show=has("item_treasure"), goto="respite",
          effects=[F("morrel_bought"), GIVE("item_red_purse")]),
    ]),
    N("respite", "act3", narration=True, end=True),
])

D("dlg_julie_purse", "Julie — the red silk purse", "npc_julie", ["conversation", "act3"], [
    N("open", "act3", contains="Sinbad", choices=[
        C("send", "Send her to the Allées de Meilhan. The purse on the mantel.",
          show=has("item_red_purse"), goto="saved",
          effects=[{"item": "item_red_purse", "type": "take_item"}]),
    ]),
    N("saved", "act3", contains="saved", end=True,
      on_enter=[F("morrel_saved"), REL("npc_morrel", 2), REL("npc_julie", 2),
                QADV("qst_mercy", "stg_mer_purse")]),
])

D("dlg_vampa_pact", "Luigi Vampa — an understanding", "npc_vampa", ["conversation", "act3"], [
    N("open", "act3", choices=[
        C("terms", "Your men spare my friends; my gold spares your men. Terms?",
          show=rep("fac_underworld", ">=", 2), goto="pact"),
        C("watch", "Say nothing. Bandits respect a man who can wait.",
          check=("nerve", 11, "pact", "later")),
    ]),
    N("pact", "act3", end=True,
      on_enter=[F("vampa_pact"), REP("fac_underworld", 1), QADV("qst_rome", "stg_rome_pact")]),
    N("later", "act3", end=True),
])

D("dlg_albert_rescue", "Albert — the catacombs of Saint Sebastian", "npc_albert", ["conversation", "act3"], [
    N("open", "act3", contains="ransom", choices=[
        C("word", "One word to Vampa, and the boy walks out untouched.",
          show=f("vampa_pact"), goto="freed"),
    ]),
    N("freed", "act3", end=True,
      on_enter=[F("albert_saved"), REL("npc_albert", 2), REP("fac_society", 1),
                QADV("qst_rome", "stg_rome_albert")]),
])

D("dlg_franz_doubt", "Franz — the man who remembers Sinbad", "npc_franz", ["conversation", "act3"], [
    N("open", "act3", choices=[
        C("deflect", "A resemblance. The world is full of hospitable islanders.",
          check=("discretion", 12, "eased", "wary")),
        C("charm", "Invite him to breakfast too. Doubt starves at a full table.", goto="eased"),
    ]),
    N("eased", "act3", end=True, on_enter=[F("franz_settled")]),
    N("wary", "act3", end=True, on_enter=[CNT("suspicion")]),
])

D("dlg_albert_invitation", "Albert — a debt, and an address in Paris", "npc_albert", ["conversation", "act3"], [
    N("open", "act3", contains="Paris", choices=[
        C("accept", "In three months, at half-past ten in the morning. Precisely.",
          goto="fixed"),
    ]),
    N("fixed", "act3", end=True,
      on_enter=[F("paris_invitation"), QADV("qst_rome", "stg_rome_invite"),
                CUT("cs_paris_entrance")]),
])

# ==================== ACT IV — PARIS: THREE THREADS AND A MERCY =============

D("dlg_paris_entrance", "The Count of Monte Cristo — Paris", None, ["object", "act4"], [
    N("open", "act4", contains="the Count of Monte Cristo", end=True,
      on_enter=[F("identity_count"), REP("fac_society", 2),
                QADV("qst_morcerf", "stg_mor_arrive")]),
])

D("dlg_albert_paris", "Albert — host and unwitting key", "npc_albert", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("family", "Let him talk of his father the Count de Morcerf. Just listen.",
          check=("discretion", 9, "learned", "learned")),
    ]),
    N("learned", "act4", end=True, on_enter=[F("knows_morcerf_house"), REL("npc_albert", 1)]),
])

D("dlg_beauchamp_press", "Beauchamp — a paragraph from Yanina", "npc_beauchamp", ["conversation", "act4"], [
    N("open", "act4", contains="Yanina", choices=[
        C("seed", "Wonder aloud what a French officer was paid for Ali Pasha's fortress.",
          show=f("knows_morcerf_house"), check=("rhetoric", 11, "printed", "waved")),
    ]),
    N("printed", "act4", end=True,
      on_enter=[F("yanina_seed"), QADV("qst_morcerf", "stg_mor_seed")]),
    N("waved", "act4", end=True),
])

D("dlg_haydee_story", "Haydée — what she saw at nine years old", "npc_haydee", ["conversation", "act4"], [
    N("open", "act4", contains="my father", choices=[
        C("ask", "Ask her — gently — whether she would say it before the Chamber.",
          show=f("yanina_seed"), goto="willing", effects=[REL("npc_haydee", 2)]),
        C("spare", "She has carried it long enough. Do not ask tonight.", goto="spared_her",
          effects=[REL("npc_haydee", 1)]),
    ]),
    N("willing", "act4", end=True,
      on_enter=[GIVE("item_yanina_dossier"), F("haydee_willing")]),
    N("spared_her", "act4", end=True),
])

D("dlg_chamber_trial", "The Chamber of Peers — the session", None, ["object", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("present", "Present the dossier and the witness.",
          show=all_(has("item_yanina_dossier"), f("haydee_willing")), goto="verdict"),
    ]),
    N("verdict", "act4", contains="Fernand", end=True,
      on_enter=[F("fernand_unmasked"), QADV("qst_morcerf", "stg_mor_unmasked"),
                REP("fac_society", -1)]),
])

D("dlg_albert_challenge", "Albert — the insult at the Opera", "npc_albert", ["conversation", "act4"], [
    N("open", "act4", contains="insult", choices=[
        C("accept", "Accept. Pistols, eight in the morning, the Bois de Vincennes.",
          goto="fixed", effects=[F("duel_pending"), QADV("qst_morcerf", "stg_mor_duel")]),
    ]),
    N("fixed", "act4", end=True),
])

D("dlg_mercedes_plea", "Mercédès — she has always known", "npc_mercedes", ["conversation", "act4"], [
    N("open", "act4", contains="Edmond", choices=[
        C("spare", "For her, then. The son will live. The father is another matter.",
          show=rel("npc_mercedes", ">=", 2), goto="spared",
          effects=[F("duel_spared"), REL("npc_mercedes", 1)]),
        C("refuse", "The dead of the Château d'If outvote her. Refuse.",
          check=("nerve", 12, "refused", "spared")),
    ]),
    N("spared", "act4", contains="son", end=True),
    N("refused", "act4", end=True, on_enter=[F("duel_hard")]),
])

D("dlg_duel_dawn", "The Bois — eight in the morning", None, ["object", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("apology", "Albert apologises before witnesses. Take it with grace.",
          show=f("duel_spared"), goto="grace"),
        C("fire", "No apology came. Take your ground.",
          show=f("duel_hard"), goto="grace"),
    ]),
    N("grace", "act4", end=True, on_enter=[F("duel_done")]),
])

D("dlg_fernand_end", "Morcerf — the last visit", "npc_fernand", ["conversation", "act4"], [
    N("open", "act4", contains="Who are you", choices=[
        C("reveal", "Take off twenty-three years as if they were a coat. Name yourself.",
          show=all_(f("knows_betrayers"), f("duel_done")), goto="named"),
    ]),
    N("named", "act4", contains="Edmond Dantès", end=True,
      on_enter=[F("fernand_ruined"), QADV("qst_morcerf", "stg_mor_ruin")]),
])

D("dlg_danglars_credit", "Danglars — six millions of credit", "npc_danglars", ["conversation", "act4"], [
    N("open", "act4", contains="million", choices=[
        C("open", "Unlimited credit, drawn how and when it pleases you to fear.",
          show=has("item_treasure"), goto="dazzled"),
    ]),
    N("dazzled", "act4", end=True,
      on_enter=[F("credit_opened"), QADV("qst_banker", "stg_ban_credit")]),
])

D("dlg_telegraph_man", "The telegraph — a gardener's price", None, ["object", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("bribe", "Twenty-five thousand francs against one wrong signal.",
          show=f("credit_opened"), check=("discretion", 10, "planted", "noticed")),
    ]),
    N("noticed", "act4", end=True, on_enter=[CNT("suspicion")]),
    N("planted", "act4", end=True,
      on_enter=[F("telegraph_planted"), GIVE("item_telegraph_note"),
                QADV("qst_banker", "stg_ban_telegraph")]),
])

D("dlg_benedetto_groom", "Andrea Cavalcanti — a prince assembled from parts", "npc_benedetto", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("coach", "Coach the counterfeit: the walk, the income, the fiancée.",
          show=f("credit_opened"), goto="ready"),
    ]),
    N("ready", "act4", end=True,
      on_enter=[F("benedetto_seeded"), REP("fac_underworld", 1),
                QADV("qst_banker", "stg_ban_benedetto")]),
])

D("dlg_mme_danglars_seance", "Madame Danglars — the house at Auteuil", "npc_mme_danglars", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("press", "Describe the garden. The tree. The box no larger than a child.",
          show=f("auteuil_told"), check=("nerve", 10, "white", "composed")),
    ]),
    N("composed", "act4", end=True),
    N("white", "act4", narration=True, end=True, on_enter=[F("mme_d_shaken")]),
])

D("dlg_eugenie", "Eugénie — the unwilling bride", "npc_eugenie", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("listen", "She wants liberty, not Cavalcanti. Note it, and note the exit it offers.",
          goto="noted", effects=[REL("npc_eugenie", 1)]),
    ]),
    N("noted", "act4", end=True, on_enter=[F("eugenie_noted")]),
])

D("dlg_danglars_ruin", "Danglars — the fifth million", "npc_danglars", ["conversation", "act4"], [
    N("open", "act4", contains="ruin", choices=[
        C("draw", "Draw the last of the six millions on the day the false signal lands.",
          show=all_(f("telegraph_planted"), f("mme_d_shaken")), goto="broken"),
    ]),
    N("broken", "act4", end=True,
      on_enter=[F("danglars_ruined"), QADV("qst_banker", "stg_ban_ruin")]),
])

D("dlg_vampa_larder", "Vampa's larder — the price of a chicken", "npc_vampa", ["conversation", "act4"], [
    N("open", "act4", contains="hundred thousand", choices=[
        C("spare", "Enough. Feed him, take the five millions for the hospitals, let him go grey.",
          show=f("danglars_ruined"), goto="mercy",
          effects=[F("danglars_spared"), QADV("qst_mercy", "stg_mer_spare")]),
        C("starve", "One more day. Hunger is an honest creditor.",
          show=f("danglars_ruined"), check=("nerve", 11, "relent", "relent")),
    ]),
    N("mercy", "act4", contains="I forgive", end=True),
    N("relent", "act4", end=True,
      on_enter=[F("danglars_spared"), QADV("qst_mercy", "stg_mer_spare")]),
])

D("dlg_bertuccio_auteuil", "Bertuccio — the garden at Auteuil", "npc_bertuccio", ["conversation", "act4"], [
    N("open", "act4", contains="Villefort", nxt="infant"),
    N("infant", "act4", narration=True, nxt="told"),
    N("told", "act4", end=True,
      on_enter=[F("auteuil_told"), QADV("qst_procureur", "stg_pro_auteuil")]),
])

D("dlg_auteuil_dinner", "Auteuil — a dinner with ghosts invited", None, ["object", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("tell", "Tell the table what was found beneath the tree in this garden.",
          show=f("auteuil_told"), check=("rhetoric", 11, "landed", "glanced")),
    ]),
    N("glanced", "act4", end=True, on_enter=[CNT("suspicion")]),
    N("landed", "act4", end=True,
      on_enter=[F("dinner_told"), QADV("qst_procureur", "stg_pro_dinner")]),
])

D("dlg_villefort_fence", "Villefort — two men measuring each other", "npc_villefort", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("probe", "Speak of justice as an instrument. Watch which word makes him still.",
          show=f("dinner_told"), check=("nerve", 13, "cracked", "smooth")),
    ]),
    N("cracked", "act4", end=True, on_enter=[F("villefort_rattled")]),
    N("smooth", "act4", end=True),
])

D("dlg_heloise_poisons", "Madame de Villefort — the chemistry lesson", "npc_heloise", ["conversation", "act4"], [
    N("open", "act4", contains="poison", choices=[
        C("teach", "Answer her questions about brucine. Precisely. Completely.",
          show=f("dinner_told"), goto="lesson"),
        C("demur", "Change the subject to harmless botany.", goto="held_back"),
    ]),
    N("lesson", "act4", end=True,
      on_enter=[F("poison_lesson"), QADV("qst_procureur", "stg_pro_lesson")]),
    N("held_back", "act4", end=True,
      on_enter=[F("poison_lesson"), QADV("qst_procureur", "stg_pro_lesson")]),
])

D("dlg_poison_watch", "The Villefort house — one death, then another", None, ["object", "act4"], [
    N("open", "act4", narration=True, nxt="pattern"),
    N("pattern", "act4", narration=True, end=True,
      on_enter=[F("household_dying"), GIVE("item_poison_vial"),
                QADV("qst_procureur", "stg_pro_dying")]),
])

D("dlg_davrigny", "Doctor d'Avrigny — a man counting symptoms", "npc_davrigny", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("show", "Show him the vial. Let science say what the house will not.",
          show=has("item_poison_vial"), goto="certain"),
        C("silent", "Let him reach it alone. He is nearly there.", goto="certain"),
    ]),
    N("certain", "act4", end=True, on_enter=[F("doctor_certain")]),
])

D("dlg_noirtier", "Noirtier — the man who speaks in blinks", "npc_noirtier", ["conversation", "act4"], [
    N("open", "act4", contains="Noirtier", choices=[
        C("ally", "Yes-blink by yes-blink, build the plan to shield Valentine.",
          show=f("household_dying"), goto="allied"),
    ]),
    N("allied", "act4", end=True, on_enter=[F("noirtier_ally"), REL("npc_valentine", 1)]),
])

D("dlg_valentine_first", "Valentine — the quiet inheritor", "npc_valentine", ["conversation", "act4"], [
    N("open", "act4", choices=[
        C("hear", "Hear what she does not say about her stepmother's kindness.",
          check=("observation", 10, "heard", "polite")),
    ]),
    N("heard", "act4", end=True, on_enter=[F("valentine_trusts"), REL("npc_valentine", 1)]),
    N("polite", "act4", end=True),
])

D("dlg_maximilien_love", "Maximilien — the vow at the gate", "npc_maximilien", ["conversation", "act4"], [
    N("open", "act4", contains="Valentine", choices=[
        C("promise", "Promise him her life on your own. Say it like a debt.",
          show=f("morrel_saved"), goto="vowed", effects=[REL("npc_maximilien", 2)]),
    ]),
    N("vowed", "act4", end=True, on_enter=[F("vowed_valentine")]),
])

D("dlg_valentine_vigil", "Valentine — the glass of water", "npc_valentine", ["conversation", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("feign", "The draught that mimics death. Noirtier's tolerance, your chemistry.",
          show=all_(f("noirtier_ally"), f("vowed_valentine"), f("valentine_trusts")),
          check=("nerve", 12, "saved", "unsteady")),
    ]),
    N("unsteady", "act4", end=True, on_enter=[CNT("suspicion")]),
    N("saved", "act4", end=True,
      on_enter=[F("valentine_saved"), QADV("qst_procureur", "stg_pro_valentine"),
                QADV("qst_mercy", "stg_mer_valentine")]),
])

D("dlg_benedetto_trial", "The assizes — the prisoner names his father", None, ["object", "act4"], [
    N("open", "act4", contains="Villefort", end=True,
      on_enter=[F("villefort_unmasked"), QADV("qst_procureur", "stg_pro_trial")]),
])

D("dlg_villefort_madness", "Villefort — the garden, digging", "npc_villefort", ["conversation", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("witness", "Say nothing. What is left of him is not listening.",
          show=f("villefort_unmasked"), goto="ash"),
    ]),
    N("ash", "act4", end=True,
      on_enter=[F("villefort_done"), QADV("qst_procureur", "stg_pro_done")]),
])

D("dlg_morrel_despair", "Maximilien — the loaded question", "npc_maximilien", ["conversation", "act4"], [
    N("open", "act4", contains="die", choices=[
        C("hope", "One month. Give me one month, and grief will owe you an apology.",
          show=f("valentine_saved"), goto="month"),
        C("truth", "Tell him now and forfeit the lesson. He has bled enough.",
          show=f("valentine_saved"), goto="month"),
    ]),
    N("month", "act4", end=True, on_enter=[F("maximilien_held"), REL("npc_maximilien", 1)]),
])

D("dlg_haydee_choice", "Haydée — free, and choosing", "npc_haydee", ["conversation", "act4"], [
    N("open", "act4", contains="love", choices=[
        C("stay", "Then stay. Not as a ward. As the reason the story continues.",
          show=rel("npc_haydee", ">=", 2), goto="stays"),
        C("free", "Give her the freedom first. Whatever she does with it.", goto="stays"),
    ]),
    N("stays", "act4", end=True, on_enter=[F("haydee_stays")]),
])

D("dlg_wait_and_hope", "Monte Cristo — the letter on the island", None, ["object", "act4"], [
    N("open", "act4", narration=True, nxt="letter"),
    N("letter", "act4", contains="wait and hope", end=True,
      on_enter=[F("story_closed"), QADV("qst_mercy", "stg_mer_letter")]),
])


D("dlg_louis_idle", "Louis Dantès — the window over the port", "npc_louis_dantes",
  ["conversation", "act1"], [N("open", "act1", end=True)])
D("dlg_beauchamp_idle", "Beauchamp — nothing printable today", "npc_beauchamp",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_mme_danglars_idle", "Madame Danglars — weather, opera, nothing", "npc_mme_danglars",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_noirtier_idle", "Noirtier — the alphabet board, idle", "npc_noirtier",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_davrigny_idle", "Doctor d'Avrigny — professional silence", "npc_davrigny",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_villefort_idle", "Villefort — the procureur is engaged", "npc_villefort",
  ["conversation", "act1"], [N("open", "act1", end=True)])
D("dlg_maximilien_idle", "Maximilien — a captain of Spahis, at ease", "npc_maximilien",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_heloise_idle", "Madame de Villefort — the garden, admired", "npc_heloise",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_albert_idle", "Albert — a prisoner keeping his manners", "npc_albert",
  ["conversation", "act3"], [N("open", "act3", end=True)])
D("dlg_franz_idle", "Franz — carnival talk", "npc_franz",
  ["conversation", "act3"], [N("open", "act3", end=True)])
D("dlg_eugenie_idle", "Eugénie — scales, practised coldly", "npc_eugenie",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_bertuccio_idle", "Bertuccio — the household accounts", "npc_bertuccio",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_julie_idle", "Julie — the happiest house in Marseilles", "npc_julie",
  ["conversation", "act3"], [N("open", "act3", end=True)])
D("dlg_benedetto_idle", "Andrea — rehearsing his own biography", "npc_benedetto",
  ["conversation", "act4"], [N("open", "act4", end=True)])
D("dlg_jailer_idle", "The jailer — no answer through the grate", "npc_jailer",
  ["conversation", "act2"], [N("open", "act2", end=True)])
D("dlg_faria_idle", "Faria — the abbé is working", "npc_faria",
  ["conversation", "act2"], [N("open", "act2", end=True)])


def G(did, title, speaker, act, rungs=2):
    """A small talk dialogue: an opening line, one aside, done."""
    D(did, title, speaker, ["gossip", act.replace("act", "act")], [
        N("open", act, choices=[
            C("more", "Let them talk. People say more to a listener than to a question.", goto="aside"),
            C("leave", "Nod, and keep your own counsel.", goto="out"),
        ]),
        N("aside", act, nxt="out"),
        N("out", act, end=True, narration=True),
    ])
    return did

# --- Reactive rungs for the major cast: the same person, changed by events.
# Effect-free like all gossip, so rungs re-visit safely. Each gate READS a
# flag the story already writes — this is the ladder mechanic doing its job.

G("dlg_mercedes_waiting", "Mercédès — the woman who waits", "npc_mercedes", "act3")
G("dlg_mercedes_widow", "Mercédès — after the house of Morcerf", "npc_mercedes", "act4")
G("dlg_danglars_shaken", "Danglars — a banker recalculating", "npc_danglars", "act4")
G("dlg_caderousse_spending", "Caderousse — how a diamond gets spent", "npc_caderousse", "act3")
G("dlg_villefort_rattled_talk", "Villefort — a man checking the locks", "npc_villefort", "act4")
G("dlg_morrel_toast", "Morrel — a toast to Sinbad the Sailor", "npc_morrel", "act3")
G("dlg_haydee_verdict", "Haydée — after the Chamber stood up", "npc_haydee", "act4")
G("dlg_maximilien_thanks", "Maximilien — the son of a saved man", "npc_maximilien", "act4")
G("dlg_beauchamp_echoes", "Beauchamp — the paragraph's echoes", "npc_beauchamp", "act4")
G("dlg_noirtier_gratitude", "Noirtier — one long, deliberate blink", "npc_noirtier", "act4")
G("dlg_bertuccio_lighter", "Bertuccio — a confession, once out", "npc_bertuccio", "act4")
G("dlg_mme_danglars_ruin", "Madame Danglars — economies, suddenly", "npc_mme_danglars", "act4")
G("dlg_eugenie_assessed", "Eugénie — the fiancé, assessed", "npc_eugenie", "act4")
G("dlg_fernand_uneasy", "Morcerf — a count reading the papers twice", "npc_fernand", "act4")
G("dlg_valentine_hidden", "Valentine — alive, and officially not", "npc_valentine", "act4")
G("dlg_jacopo_captain", "Jacopo — a captain with his own deck", "npc_jacopo", "act3")

# ===================== CHARACTERS — ladders, most specific rung first =======
def CH(cid, name, desc, ladder):
    for rung in ladder:
        if "showIf" in rung: _scan_cond(rung["showIf"])
    FILES[f"data/characters/{cid}.json"] = {
        "description": desc, "dialogues": ladder, "id": cid, "name": name, "role": desc}

def R(did, show=None):
    return {"dialogue": did, "showIf": show} if show else {"dialogue": did}

CH("npc_morrel", "M. Morrel", "Owner of the Pharaon. Decency with a ledger it cannot quite balance.", [
    R("dlg_morrel_toast", f("morrel_saved")), R("dlg_morrel_rescue", f("identity_wilmore")), R("dlg_morrel_first")])
CH("npc_danglars", "Danglars", "Supercargo, then baron. Counts everything, including favours.", [
    R("dlg_danglars_ruin", f("telegraph_planted")),
    R("dlg_danglars_shaken", f("mme_d_shaken")),
    R("dlg_danglars_credit", f("identity_count")), R("dlg_danglars_first")])
CH("npc_caderousse", "Caderousse", "A tailor with debts, then an innkeeper with worse.", [
    R("dlg_caderousse_spending", f("gave_diamond")), R("dlg_caderousse_diamond", f("identity_busoni")), R("dlg_caderousse_first")])
CH("npc_villefort", "Villefort", "Deputy procureur. Ambitious in the way that costs other people.", [
    R("dlg_villefort_madness", f("villefort_unmasked")),
    R("dlg_villefort_rattled_talk", f("villefort_rattled")),
    R("dlg_villefort_fence", f("identity_count")),
    R("dlg_villefort_interrogation", f("arrested")), R("dlg_villefort_idle")])
CH("npc_mercedes", "Mercédès", "Of the Catalans. The only person in Paris who was in Marseilles.", [
    R("dlg_mercedes_widow", f("fernand_ruined")), R("dlg_mercedes_plea", f("duel_pending")), R("dlg_mercedes_waiting", f("identity_wilmore")), R("dlg_mercedes_first")])
CH("npc_fernand", "Fernand", "A fisherman, then a count. The distance between is Yanina.", [
    R("dlg_fernand_end", f("duel_done")), R("dlg_fernand_uneasy", f("yanina_seed")), R("dlg_fernand_first")])
CH("npc_louis_dantes", "Louis Dantès", "Edmond's father. Pride, and an empty cupboard hidden behind it.", [
    R("dlg_louis_father", f("greeted_father", False)), R("dlg_louis_idle")])
CH("npc_jailer", "The Jailer", "Soup at the same hour for fourteen years.", [R("dlg_jailer", f("in_cell")), R("dlg_jailer_idle")])
CH("npc_faria", "Abbé Faria", "A prisoner who made a library of his own memory.", [
    R("dlg_faria_death", f("knows_treasure")),
    R("dlg_faria_treasure", f("knows_betrayers")),
    R("dlg_faria_deduce", f("edu_2")),
    R("dlg_faria_teach_2", f("edu_1")),
    R("dlg_faria_teach_1"), R("dlg_faria_idle")])
CH("npc_jacopo", "Jacopo", "A smuggler who pulled a stranger from the sea and never regretted it.", [
    R("dlg_jacopo_captain", f("jacopo_loyal")), R("dlg_jacopo_farewell", has("item_treasure")), R("dlg_jacopo_rescue")])
CH("npc_vampa", "Luigi Vampa", "Bandit chief. Keeps his word for his own reasons.", [
    R("dlg_vampa_larder", f("danglars_ruined")), R("dlg_vampa_pact")])
CH("npc_franz", "Franz d'Épinay", "Albert's friend. Remembers an island, and a host with no name.", [
    R("dlg_franz_doubt", f("franz_settled", False)), R("dlg_franz_idle")])
CH("npc_albert", "Albert de Morcerf", "Fernand's son, and none of Fernand's crimes.", [
    R("dlg_albert_challenge", f("fernand_unmasked")),
    R("dlg_albert_paris", f("identity_count")),
    R("dlg_albert_invitation", f("albert_saved")),
    R("dlg_albert_rescue", f("vampa_pact")), R("dlg_albert_idle")])
CH("npc_haydee", "Haydée", "Daughter of Ali Pasha. Sold once; never again.", [
    R("dlg_haydee_choice", f("fernand_ruined")),
    R("dlg_haydee_verdict", f("fernand_unmasked")),
    R("dlg_haydee_story")])
CH("npc_beauchamp", "Beauchamp", "A journalist who checks twice and prints once.", [
    R("dlg_beauchamp_echoes", f("yanina_seed")), R("dlg_beauchamp_press", all_(f("identity_count"), f("yanina_seed", False))), R("dlg_beauchamp_idle")])
CH("npc_mme_danglars", "Madame Danglars", "The baroness. Auteuil is a word she cannot hear calmly.", [
    R("dlg_mme_danglars_ruin", f("danglars_ruined")), R("dlg_mme_danglars_seance", all_(f("auteuil_told"), f("mme_d_shaken", False))), R("dlg_mme_danglars_idle")])
CH("npc_eugenie", "Eugénie Danglars", "Would rather have a career than a husband, and says so.", [
    R("dlg_eugenie_assessed", f("benedetto_seeded")), R("dlg_eugenie", f("eugenie_noted", False)), R("dlg_eugenie_idle")])
CH("npc_benedetto", "Andrea Cavalcanti", "A forger's masterpiece: a prince made of paper.", [
    R("dlg_benedetto_groom", f("benedetto_seeded", False)), R("dlg_benedetto_idle")])
CH("npc_bertuccio", "Bertuccio", "A steward with one confession, kept like a scar.", [
    R("dlg_bertuccio_lighter", f("dinner_told")), R("dlg_bertuccio_auteuil", f("auteuil_told", False)), R("dlg_bertuccio_idle")])
CH("npc_heloise", "Madame de Villefort", "A stepmother with an interest in chemistry.", [
    R("dlg_heloise_poisons", all_(f("dinner_told"), f("poison_lesson", False))), R("dlg_heloise_idle")])
CH("npc_valentine", "Valentine de Villefort", "The inheritor every death in the house points toward.", [
    R("dlg_valentine_hidden", f("valentine_saved")),
    R("dlg_valentine_vigil", f("household_dying")),
    R("dlg_valentine_first")])
CH("npc_noirtier", "Noirtier", "Paralysed entirely, except for everything that matters.", [
    R("dlg_noirtier_gratitude", f("valentine_saved")), R("dlg_noirtier", all_(f("household_dying"), f("noirtier_ally", False))), R("dlg_noirtier_idle")])
CH("npc_maximilien", "Maximilien Morrel", "The son of the man the red purse saved.", [
    R("dlg_morrel_despair", f("villefort_unmasked")),
    R("dlg_maximilien_love", f("household_dying")),
    R("dlg_maximilien_thanks", f("morrel_saved")), R("dlg_maximilien_idle")])
CH("npc_davrigny", "Doctor d'Avrigny", "A physician counting symptoms he was not meant to see.", [
    R("dlg_davrigny", all_(f("household_dying"), f("doctor_certain", False))), R("dlg_davrigny_idle")])
CH("npc_julie", "Julie Morrel", "Sent to a mantelpiece by a stranger's letter, and found a fortune.", [
    R("dlg_julie_purse", f("morrel_bought")), R("dlg_julie_idle")])

# ===================== LOCATIONS ===========================================
def L(lid, name, zone, npcs=None, objects=None, exits=None, tags=None):
    inter = []
    for c in npcs or []:
        cid, show = (c, None) if isinstance(c, str) else c
        it = {"character": cid, "id": f"int_{lid}_{cid}", "kind": "npc"}
        if show: it["showIf"] = show; _scan_cond(show)
        inter.append(it)
    for o in objects or []:
        it = {"dialogue": o["d"], "id": f"int_{lid}_{o['d']}", "kind": "object"}
        if o.get("show"): it["showIf"] = o["show"]; _scan_cond(o["show"])
        if o.get("enter"): it["trigger"] = "on_enter"
        inter.append(it)
    exs = []
    for e in exits or []:
        ex = {"id": f"ex_{lid}_{e['to']}", "to": {"location": e["to"], "spawn": f"sp_{e['to']}"}}
        if e.get("gate"):
            ex["gate"] = e["gate"]; ex["gateType"] = "act_gate"; _scan_cond(e["gate"])
            if e.get("denial"): ex["denialDialogue"] = e["denial"]
        exs.append(ex)
    FILES[f"data/locations/{lid}.json"] = {
        "description": narr("act1" if "act" not in (tags or []) else tags[0]),
        "exits": exs, "id": lid, "interactables": inter, "name": name,
        "spawns": [{"id": f"sp_{lid}", "isDefault": True}], "tags": tags or [], "zone": zone}

L("loc_harbour", "The Marseilles Quay", "zone_marseilles",
  npcs=["npc_louis_dantes", "npc_caderousse"],
  objects=[{"d": "dlg_harbour_landing", "enter": True}],
  exits=[{"to": "loc_pharaon"}, {"to": "loc_catalans"}, {"to": "loc_morrel_office"},
         {"to": "loc_reserve", "gate": f("betrothed"), "denial": "dlg_harbour_landing"},
         {"to": "loc_palais", "gate": f("arrested")},
         {"to": "loc_isle", "gate": f("identity_wilmore")}],
  tags=["start"])
L("loc_pharaon", "The Pharaon — deck", "zone_marseilles",
  objects=[{"d": "dlg_pharaon_deck"}], exits=[{"to": "loc_harbour"}])
L("loc_catalans", "The Catalans", "zone_marseilles",
  npcs=["npc_mercedes", "npc_fernand"], exits=[{"to": "loc_harbour"}])
L("loc_morrel_office", "Morrel & Son", "zone_marseilles",
  npcs=["npc_morrel", "npc_danglars", ("npc_julie", f("morrel_bought"))],
  exits=[{"to": "loc_harbour"}])
L("loc_reserve", "La Réserve", "zone_marseilles",
  objects=[{"d": "dlg_reserve_feast", "enter": True, "show": f("betrothed")}],
  exits=[{"to": "loc_harbour"}, {"to": "loc_palais", "gate": f("arrested")}])
L("loc_palais", "The Palais de Justice", "zone_marseilles",
  npcs=["npc_villefort"], objects=[],
  exits=[{"to": "loc_reserve"}, {"to": "loc_harbour"},
         {"to": "loc_if_cell", "gate": f("condemned")}])
L("loc_if_cell", "The Château d'If — cell 34", "zone_prison",
  npcs=["npc_jailer"],
  objects=[{"d": "dlg_cell_arrival", "enter": True},
           {"d": "dlg_scratching", "show": {"counter": "years", "op": ">=", "type": "counter", "value": 1}},
           {"d": "dlg_faria_meet", "show": f("heard_scratching")}],
  exits=[{"to": "loc_faria_cell", "gate": f("met_faria")}])
L("loc_faria_cell", "The abbé's cell", "zone_prison",
  npcs=["npc_faria"],
  objects=[{"d": "dlg_shroud", "show": f("faria_dead")}],
  exits=[{"to": "loc_if_cell"},
         {"to": "loc_isle", "gate": f("escaped")}])
L("loc_isle", "The Isle of Monte Cristo", "zone_sea",
  npcs=["npc_jacopo"],
  objects=[{"d": "dlg_isle_landing", "enter": True, "show": f("aboard_amelie")},
           {"d": "dlg_grotto", "show": f("knows_treasure")},
           {"d": "dlg_busoni_donning", "show": has("item_treasure")},
           {"d": "dlg_wilmore_donning", "show": has("item_treasure")},
           {"d": "dlg_wait_and_hope", "show": all_(f("villefort_done"), f("fernand_ruined"), f("danglars_ruined"))}],
  exits=[{"to": "loc_pont_inn", "gate": f("identity_busoni")},
         {"to": "loc_harbour", "gate": f("identity_wilmore")},
         {"to": "loc_rome", "gate": all_(has("item_treasure"), f("jacopo_loyal"))}])
L("loc_pont_inn", "The inn at Pont du Gard", "zone_road",
  npcs=["npc_caderousse"], exits=[{"to": "loc_isle"}, {"to": "loc_rome"}])
L("loc_rome", "Rome — carnival and catacombs", "zone_italy",
  npcs=["npc_vampa", "npc_franz", "npc_albert"],
  exits=[{"to": "loc_isle"},
         {"to": "loc_paris_salon", "gate": f("paris_invitation")}])
L("loc_paris_salon", "The Champs-Élysées house", "zone_paris",
  npcs=["npc_albert", "npc_haydee", "npc_beauchamp",
        ("npc_mercedes", f("duel_pending")), ("npc_fernand", f("fernand_unmasked"))],
  objects=[{"d": "dlg_paris_entrance", "enter": True, "show": f("paris_invitation")},
           {"d": "dlg_chamber_trial", "show": all_(f("haydee_willing"), rep("fac_society", ">=", 2))},
           {"d": "dlg_benedetto_trial", "show": all_(f("danglars_ruined"), f("benedetto_seeded"))},
           {"d": "dlg_duel_dawn", "show": f("duel_pending")}],
  exits=[{"to": "loc_danglars_bank"}, {"to": "loc_villefort_house"}, {"to": "loc_auteuil"},
         {"to": "loc_rome", "gate": f("identity_count")},
         {"to": "loc_isle", "gate": f("villefort_done")}])
L("loc_danglars_bank", "The Danglars bank", "zone_paris",
  npcs=["npc_danglars", "npc_mme_danglars", "npc_eugenie", "npc_benedetto"],
  objects=[{"d": "dlg_telegraph_man", "show": f("credit_opened")}],
  exits=[{"to": "loc_paris_salon"}])
L("loc_villefort_house", "The Villefort house", "zone_paris",
  npcs=["npc_villefort", "npc_heloise", "npc_valentine", "npc_noirtier",
        "npc_maximilien", "npc_davrigny"],
  objects=[{"d": "dlg_poison_watch", "show": f("poison_lesson")}],
  exits=[{"to": "loc_paris_salon"}, {"to": "loc_auteuil"}])
L("loc_auteuil", "The house at Auteuil", "zone_paris",
  npcs=["npc_bertuccio"],
  objects=[{"d": "dlg_auteuil_dinner", "show": f("auteuil_told")}],
  exits=[{"to": "loc_paris_salon"}, {"to": "loc_villefort_house"}])

# ===================== QUESTS ==============================================
def Q(qid, name, summary, stages, outcomes, available=None, starts=False):
    stg = []
    for i, (sid, cw, obj_text) in enumerate(stages):
        _scan_cond(cw)
        stg.append({"completeWhen": cw, "description": narr("act4"),
                    "id": sid, "objectives": [{"id": f"obj_{sid}", "text": obj_text}],
                    "order": i + 1})
    # Dependency-graph edges are derived from flags a quest PRODUCES
    # (stage.onComplete / outcome.effects) against flags a later quest's
    # availableWhen NEEDS. Dialogue-written flags are invisible to that
    # derivation, so each quest emits its own completion marker. Prefer the
    # success outcome, else the first — qst_arrest completes by failing.
    _marked = next((o for o in outcomes if o["kind"] == "success"), outcomes[0])
    _marked.setdefault("effects", []).append(F(f"{qid}_complete"))
    for o in outcomes:
        _scan_cond(o["reachedWhen"])
        _scan_effects(o.get("effects"), f"{qid}/{o['id']}")
    quest = {"id": qid, "journalName": name, "name": name, "outcomes": outcomes,
             "stages": stg, "summary": summary, "tags": ["main"]}
    if starts: quest["startsAvailable"] = True
    if available: quest["availableWhen"] = available; _scan_cond(available)
    FILES[f"data/quests/{qid}.json"] = quest

def OC(oid, kind, when, xp=0):
    o = {"description": narr("act4"), "id": oid, "kind": kind, "reachedWhen": when}
    if xp: o["effects"] = [XP(xp)]
    return o

Q("qst_pharaon", "The Homecoming", "The Pharaon is home and her captain is not.", [
    ("stg_pha_dock", f("came_ashore"), "Bring the Pharaon to her mooring."),
    ("stg_pha_report", f("met_morrel"), "Give the owner the voyage, plainly."),
    ("stg_pha_captain", f("made_captain"), "See M. Morrel about the captaincy."),
], [OC("out_captain", "success", f("made_captain"), xp=50)], starts=True)

Q("qst_betrothal", "The Marriage Feast", "Mercédès said yes before the ship had docked.", [
    ("stg_bet_feast", f("betrothed"), "Ask her properly, at the Catalans."),
], [OC("out_betrothed", "success", f("betrothed"))],
  available=f("qst_pharaon_complete"))

Q("qst_conspiracy", "Three Men at a Table", "Envy, jealousy, and a man too drunk to object.", [
    ("stg_con_danglars", f("noticed_danglars"), "Watch Danglars when the captaincy is mentioned."),
    ("stg_con_fernand", f("noticed_fernand"), "Watch Fernand's hands, not his mouth."),
    ("stg_con_warning", f("warned_by_caderousse"), "Listen to Caderousse past his third glass."),
], [OC("out_eyes_open", "success",
        all_(f("noticed_danglars"), f("noticed_fernand"),
             {"counter": "suspicion", "op": ">=", "type": "counter", "value": 2}))],
  available=f("qst_pharaon_complete"))

Q("qst_arrest", "The King's Attorney", "A knock at the feast, and a room above the harbour.", [
    ("stg_arr_seized", f("arrested"), "Answer the soldiers at La Réserve."),
    ("stg_arr_letter", f("letter_burned"), "Answer Villefort about the letter."),
    ("stg_arr_cell", f("in_cell"), "Count the steps down to cell 34."),
], [OC("out_buried", "failure", f("in_cell"))],
  available=f("qst_betrothal_complete"))

Q("qst_tunnel", "The Sound in the Wall", "Fourteen inches of stone, and something on the other side.", [
    ("stg_tun_sound", f("heard_scratching"), "Make sense of the scratching."),
    ("stg_tun_meet", f("met_faria"), "Answer it."),
], [OC("out_companion", "success", f("met_faria"), xp=50)],
  available=f("qst_arrest_complete"))

Q("qst_education", "The Second Life", "Everything Faria knows, poured into the years.", [
    ("stg_edu_tongues", f("edu_1"), "Languages, first."),
    ("stg_edu_sciences", f("edu_2"), "Then everything else."),
    ("stg_edu_deduction", f("knows_betrayers"), "Then the one deduction that matters."),
], [OC("out_scholar", "success", f("knows_betrayers"), xp=200)],
  available=f("qst_tunnel_complete"))

Q("qst_escape", "The Only Door", "Nobody leaves the Château d'If alive. Precisely.", [
    ("stg_esc_dead", f("faria_dead"), "Bury your friend."),
    ("stg_esc_shroud", f("escaped"), "Take his place."),
    ("stg_esc_amelie", f("aboard_amelie"), "Be someone else by the time you are pulled from the sea."),
], [OC("out_free", "success", f("aboard_amelie"), xp=100)],
  available=f("qst_education_complete"))

Q("qst_treasure", "The Spada Fortune", "An arithmetic of caverns and ingots, tested against rock.", [
    ("stg_tre_secret", f("knows_treasure"), "Hear the abbé out."),
    ("stg_tre_isle", f("on_isle"), "Reach the island alone."),
    ("stg_tre_found", has("item_treasure"), "The second opening, the far corner."),
], [OC("out_rich", "success", has("item_treasure"), xp=100)],
  available=f("qst_escape_complete"))

Q("qst_diamond", "The Priest's Diamond", "One stone, offered to a man's conscience to see which wins.", [
    ("stg_dia_donned", f("identity_busoni"), "Become the Abbé Busoni."),
    ("stg_dia_tale", f("heard_inn_tale"), "Hear what became of everyone."),
], [OC("out_tested", "success", f("heard_inn_tale")),
    OC("out_given", "neutral", f("gave_diamond"), xp=50)],
  available=f("qst_treasure_complete"))

Q("qst_rome", "The Roman Door", "Paris does not open to money. It opens to a story.", [
    ("stg_rome_pact", f("vampa_pact"), "Come to terms with Vampa."),
    ("stg_rome_albert", f("albert_saved"), "Let the Morcerf boy owe you his life."),
    ("stg_rome_invite", f("paris_invitation"), "Accept breakfast, three months hence, precisely."),
], [OC("out_doors", "success", f("paris_invitation"), xp=50)],
  available=f("qst_treasure_complete"))

Q("qst_morcerf", "Yanina", "What a French officer sold, and what his son must not pay for.", [
    ("stg_mor_arrive", f("identity_count"), "Arrive in Paris as the Count."),
    ("stg_mor_seed", f("yanina_seed"), "Put one paragraph where Beauchamp will find it."),
    ("stg_mor_unmasked", f("fernand_unmasked"), "Let the Chamber hear a witness."),
    ("stg_mor_duel", f("duel_done"), "Meet the son at eight in the morning."),
    ("stg_mor_ruin", f("fernand_ruined"), "Show the father twenty-three years, all at once."),
], [OC("out_fernand", "success", f("fernand_ruined"), xp=50)],
  available=f("qst_rome_complete"))

Q("qst_banker", "Six Millions of Credit", "Ruin a banker with nothing but his own arithmetic.", [
    ("stg_ban_credit", f("credit_opened"), "Open the unlimited account."),
    ("stg_ban_telegraph", f("telegraph_planted"), "Buy one wrong signal."),
    ("stg_ban_benedetto", f("benedetto_seeded"), "Supply a son-in-law of quality."),
    ("stg_ban_ruin", f("danglars_ruined"), "Let the fifth million do its work."),
], [OC("out_danglars", "success", f("danglars_ruined"), xp=50)],
  available=f("qst_rome_complete"))

Q("qst_procureur", "The House of Villefort", "Justice, applied at last to the man who dispensed it.", [
    ("stg_pro_auteuil", f("auteuil_told"), "Hear Bertuccio's confession."),
    ("stg_pro_dinner", f("dinner_told"), "Serve the garden's history at dinner."),
    ("stg_pro_lesson", f("poison_lesson"), "Answer Madame's questions about brucine."),
    ("stg_pro_dying", f("household_dying"), "Count the deaths as the house does not."),
    ("stg_pro_valentine", f("valentine_saved"), "Keep Valentine out of the arithmetic."),
    ("stg_pro_trial", f("villefort_unmasked"), "Attend the assizes."),
    ("stg_pro_done", f("villefort_done"), "See what is left in the garden."),
], [OC("out_villefort", "success", f("villefort_done"), xp=50)],
  available=f("qst_rome_complete"))

Q("qst_mercy", "What Is Owed", "Vengeance keeps accounts. So does the other thing.", [
    ("stg_mer_purse", f("morrel_saved"), "The red purse, on the mantel, as it once was."),
    ("stg_mer_valentine", f("valentine_saved"), "One life kept out of the ledger."),
    ("stg_mer_spare", f("danglars_spared"), "Leave one man alive to be old."),
    ("stg_mer_letter", f("story_closed"), "Write the letter, and leave it on the island."),
], [OC("out_mercy", "success", all_(f("danglars_spared"), f("valentine_saved")))],
  available=f("qst_rome_complete"))

# ===================== ENDINGS =============================================
def E(eid, kind, name, when):
    _scan_cond(when)
    FILES[f"data/endings/{eid}.json"] = {"id": eid, "kind": kind, "name": name,
        "summary": narr("act4"), "tags": ["ending"], "unlockedBy": when}

E("ending_wait_and_hope", "success", "Wait and Hope",
  all_(qo("qst_morcerf", "out_fernand"), qo("qst_banker", "out_danglars"),
       qo("qst_procureur", "out_villefort"), qo("qst_mercy", "out_mercy"),
       f("story_closed"), f("haydee_stays"), f("maximilien_held")))
E("ending_avenger", "neutral", "The Avenger",
  all_(qo("qst_morcerf", "out_fernand"), qo("qst_banker", "out_danglars"),
       qo("qst_procureur", "out_villefort"), f("story_closed"),
       f("danglars_spared", False)))
E("ending_poison_wins", "failure", "The Glass of Water",
  all_(q("qst_procureur", ">=", "stg_pro_trial"), f("valentine_saved", False)))

# ===================== CODEX / CUTSCENES / LORE ============================
def CX(cid, name, cat, body, when):
    _scan_cond(when)
    FILES[f"data/codex/{cid}.json"] = {"body": body, "category": cat, "id": cid,
        "name": name, "tags": [], "unlockedBy": when}

CX("codex_pharaon", "The Pharaon", "world",
   "Three-master out of Marseilles. Came home with her captain dead and her future first mate aboard.", f("made_captain"))
CX("codex_hundred_days", "The Hundred Days", "world",
   "The Emperor is on Elba, then he is not. For one season every letter in France is a loaded pistol.", f("took_letter"))
CX("codex_chateau_dif", "The Château d'If", "world",
   "A fortress on a rock. Prisoners arrive by boat and leave by the cemetery, which is the sea.", f("in_cell"))
CX("codex_spada", "The Spada Fortune", "evidence",
   "A cardinal's hoard, hidden from a Borgia and everyone since. Faria's arithmetic says the second grotto.", f("knows_treasure"))
CX("codex_telegraph", "The Semaphore Telegraph", "evidence",
   "Signals relayed tower to tower by men who cannot read them. Twenty-five thousand francs buys one wrong arm.", has("item_telegraph_note"))
CX("codex_yanina", "Yanina", "evidence",
   "A fortress sold, a pasha betrayed, a daughter sold after him. The buyer's name is now a French title.", has("item_yanina_dossier"))
CX("codex_procureur", "The Procureur's Face", "evidence",
   "Justice as an instrument. Say the word 'Auteuil' and watch which muscle moves first.", f("villefort_rattled"))
CX("codex_brucine", "Brucine", "evidence",
   "A tonic in drops, a verdict in spoonfuls. Tolerance can be trained — Noirtier's physician knows how.", f("doctor_certain"))

FILES["data/cutscenes/cs_escape_shroud.json"] = {
    "arrivesAt": {"location": "loc_isle", "spawn": "sp_loc_isle"},
    "asset": "Cutscenes/EscapeShroud", "effectsOnComplete": [],
    "entersDialogue": "dlg_jacopo_rescue",
    "id": "cs_escape_shroud", "name": "The Cemetery of the Château d'If", "skippable": False}
FILES["data/cutscenes/cs_paris_entrance.json"] = {
    "arrivesAt": {"location": "loc_paris_salon", "spawn": "sp_loc_paris_salon"},
    "asset": "Cutscenes/ParisEntrance", "effectsOnComplete": [],
    "entersDialogue": "dlg_paris_entrance",
    "id": "cs_paris_entrance", "name": "Number 30, Champs-Élysées", "skippable": True}

FILES["data/progression.json"] = {
    "maxSkill": 8, "pointsPerLevel": 1,
    "startingSkills": {"discretion": 1, "nerve": 2, "observation": 2, "rhetoric": 2},
    "xpThresholds": [0, 100, 250, 450, 700]}

# ===================== GOSSIP & WORLD TEXTURE ==============================
# Effect-free by design: gossip observes the world, never advances it. That
# keeps every rung re-visitable without retire-gates, and makes the ladders a
# clean demonstration — the same person says different things as the story
# moves, chosen by first-match-wins over world state.


# --- Marseilles: the quay talks, and later remembers --------------------
G("dlg_penelon_pharaon", "Penelon — quay talk: the voyage home", "npc_penelon", "act1")
G("dlg_penelon_affair", "Penelon — the Dantès affair, years on", "npc_penelon", "act3")
CH("npc_penelon", "Penelon", "Sailor of the Pharaon. Chews tobacco and history in equal measure.", [
    R("dlg_penelon_affair", f("identity_wilmore")),
    R("dlg_penelon_pharaon")])

G("dlg_carconte_sour", "La Carconte — the inn's thin ledger", "npc_carconte", "act3")
G("dlg_carconte_diamond", "La Carconte — arithmetic about a diamond", "npc_carconte", "act3")
CH("npc_carconte", "La Carconte", "Caderousse's wife. Fever-eyed, and quicker at sums than her husband.", [
    R("dlg_carconte_diamond", f("gave_diamond")),
    R("dlg_carconte_sour")])

# --- Rome: an innkeeper who narrates bandits ----------------------------
G("dlg_pastrini_vampa", "Pastrini — the legend of Luigi Vampa", "npc_pastrini", "act3")
G("dlg_pastrini_rescue", "Pastrini — how the French boy was saved", "npc_pastrini", "act3")
CH("npc_pastrini", "Signor Pastrini", "Master of the Hôtel de Londres. Sells rooms, meals, and legends.", [
    R("dlg_pastrini_rescue", f("albert_saved")),
    R("dlg_pastrini_vampa")])

# --- Paris: the salons react to every move ------------------------------
G("dlg_debray_ministry", "Debray — ministry small talk", "npc_debray", "act4")
G("dlg_debray_credit", "Debray — six millions, they say", "npc_debray", "act4")
G("dlg_debray_telegraph", "Debray — a curious error at the telegraph", "npc_debray", "act4")
CH("npc_debray", "Lucien Debray", "Secretary at the Ministry. Trades information at better rates than the Bourse.", [
    R("dlg_debray_telegraph", f("telegraph_planted")),
    R("dlg_debray_credit", f("credit_opened")),
    R("dlg_debray_ministry")])

G("dlg_renaud_club", "Château-Renaud — club talk", "npc_renaud", "act4")
G("dlg_renaud_count", "Château-Renaud — who IS this Count?", "npc_renaud", "act4")
G("dlg_renaud_scandal", "Château-Renaud — the Morcerf scandal", "npc_renaud", "act4")
CH("npc_renaud", "Château-Renaud", "Baron, clubman, reliable barometer of what Paris will say tomorrow.", [
    R("dlg_renaud_scandal", f("fernand_unmasked")),
    R("dlg_renaud_count", f("identity_count")),
    R("dlg_renaud_club")])

G("dlg_barrois_habits", "Barrois — the old gentleman's routine", "npc_barrois", "act4")
G("dlg_barrois_deaths", "Barrois — a servant counts the funerals", "npc_barrois", "act4")
CH("npc_barrois", "Barrois", "Noirtier's old servant. Loyal to the man, not the household.", [
    R("dlg_barrois_deaths", f("household_dying")),
    R("dlg_barrois_habits")])

# --- Ambient rumor objects ----------------------------------------------
D("dlg_quay_rumors", "The quay — what Marseilles is saying", None, ["gossip", "act1"], [
    N("open", "act1", narration=True, choices=[
        C("bona", "Listen to the Bonapartist tables.", goto="tables",
          show=rep("fac_bonapartist", ">=", 1)),
        C("any", "Listen to whoever is loudest.", goto="tables"),
    ]),
    N("tables", "act1", nxt="done"),
    N("done", "act1", end=True, narration=True),
])
D("dlg_salon_rumors", "The salon — what Paris is saying", None, ["gossip", "act4"], [
    N("open", "act4", narration=True, choices=[
        C("listen", "Circulate. Collect sentences the way other men collect debts.", goto="round"),
        C("scandal", "Steer the room toward Yanina, gently.", goto="steered",
          show=f("yanina_seed")),
    ]),
    N("round", "act4", nxt="done"),
    N("steered", "act4", nxt="done"),
    N("done", "act4", end=True, narration=True),
])

# Place the new cast.
for _rel, _obj in FILES.items():
    if _rel == "data/locations/loc_harbour.json":
        _obj["interactables"].insert(0, {"character": "npc_penelon", "id": "int_loc_harbour_npc_penelon", "kind": "npc"})
        _obj["interactables"].append({"dialogue": "dlg_quay_rumors", "id": "int_loc_harbour_rumors", "kind": "object"})
    if _rel == "data/locations/loc_pont_inn.json":
        _obj["interactables"].append({"character": "npc_carconte", "id": "int_loc_pont_inn_npc_carconte", "kind": "npc"})
    if _rel == "data/locations/loc_rome.json":
        _obj["interactables"].append({"character": "npc_pastrini", "id": "int_loc_rome_npc_pastrini", "kind": "npc"})
    if _rel == "data/locations/loc_paris_salon.json":
        _obj["interactables"].append({"character": "npc_debray", "id": "int_loc_paris_salon_npc_debray", "kind": "npc"})
        _obj["interactables"].append({"character": "npc_renaud", "id": "int_loc_paris_salon_npc_renaud", "kind": "npc"})
        _obj["interactables"].append({"dialogue": "dlg_salon_rumors", "id": "int_loc_paris_salon_rumors", "kind": "object"})
    if _rel == "data/locations/loc_villefort_house.json":
        _obj["interactables"].append({"character": "npc_barrois", "id": "int_loc_villefort_house_npc_barrois", "kind": "npc"})

# --- World-lore codex, unlocked by things the player has done ------------
CX("codex_catalans", "The Catalans", "world",
   "A village of Spanish fishing families on the tongue of land past the Fort. They marry inward, remember everything, and bury their own.", f("betrothed"))
CX("codex_carnival", "The Roman Carnival", "world",
   "Eight days when Rome wears a mask and the Corso runs with confetti and moccoletti. An excellent week to move unnoticed, or to disappear a viscount.", f("albert_saved"))
CX("codex_chamber", "The Chamber of Peers", "world",
   "France's upper house: titles, rentes, and reputations. It cannot try a man for Yanina, but it can stop standing when he enters.", f("fernand_unmasked"))
CX("codex_smugglers", "The Free Traders of the Coast", "world",
   "Genoa to Marseilles, the little ships run silk, tobacco, and men without papers. They ask no questions a paying passenger does not raise.", f("aboard_amelie"))

# --- Read-only lore documents -------------------------------------------
LORE_EXTRA = {
"world-of-1815.md": """# France, 1815 — the ground the story stands on

Read-only canon. The editor shows this in the lore panel; the runtime never
loads it.

## The two Frances

The Emperor is on Elba and every dinner table in Marseilles is two tables.
The royalists hold the offices and the shipping money; the Bonapartists hold
the docks, half the army lists, and their tongues — badly. A letter with the
wrong address is not correspondence, it is evidence.

## Marseilles

A port first and a city second. Fortunes are cargoes: one safe voyage of the
Pharaon keeps a house of clerks fed for a year, and one lost letter of
credit can end a house older than the harbour chain. The Crown's eyes in the
city are the procureur's office — and the procureur's office is one ambitious
deputy whose own father is on the wrong list.

## The Château d'If

A white rock a mile off the harbour with a fortress grown into it. Officially
a prison for men awaiting trial; actually a place where files go to stop
being read. Prisoners arrive by boat at night. The registry is accurate,
which is not the same as consulted.
""",
"paris-1838.md": """# Paris, 1838 — the second board

Read-only canon. The editor shows this in the lore panel; the runtime never
loads it.

## Money is the new blood

The Restoration gave the titles back; the July Monarchy priced them. A baron
of the Bourse outbids a count of the Crusades, and both of them borrow. The
season runs on credit, marriages are mergers, and the Opera is the exchange
floor where the real quotations are read from boxes.

## The instruments

The semaphore telegraph moves a fact faster than a horse, so a false fact
moves at the same speed. The newspapers print what survives a duel. The
Chamber of Peers seats men whose biographies stop, carefully, at 1815.

## The Count

Nobody knows him, which in Paris is a credential. He pays in gold, dines
never, and knows everyone's second secret. Society has decided he is a
prince, a smuggler, or a ghost — and invites him regardless, because the
alternative is not knowing what happens at his table.
""",
}


# ===================== ROUTES: scene-to-scene jumps =========================
# `set_active_dialogue` re-points a character's ladder at a specific next
# conversation — "after this, they want to talk about that". It is also what
# the editor's flow map draws its edges from, so a story whose connections
# live only in ladder gates analyses as N disconnected scenes.
#
# Each route: the SOURCE dialogue's terminal beats pin the character; the
# TARGET's rung accepts the pin as an alternative to its story condition, and
# clears it on the way out. One pin per character at a time — the flag is a
# boolean, so these are single hops, never chains.

ROUTE_LIST = [
    # (source dialogue, character, target dialogue)
    ("dlg_faria_meet",        "npc_faria",       "dlg_faria_teach_1"),
    ("dlg_faria_teach_1",     "npc_faria",       "dlg_faria_teach_2"),
    ("dlg_faria_deduce",      "npc_faria",       "dlg_faria_treasure"),
    ("dlg_albert_rescue",     "npc_albert",      "dlg_albert_invitation"),
    ("dlg_chamber_trial",     "npc_haydee",      "dlg_haydee_verdict"),
    ("dlg_beauchamp_press",   "npc_beauchamp",   "dlg_beauchamp_echoes"),
    ("dlg_auteuil_dinner",    "npc_bertuccio",   "dlg_bertuccio_lighter"),
    ("dlg_benedetto_trial",   "npc_villefort",   "dlg_villefort_madness"),
    ("dlg_poison_watch",      "npc_davrigny",    "dlg_davrigny"),
    ("dlg_valentine_vigil",   "npc_maximilien",  "dlg_morrel_despair"),
        ("dlg_danglars_ruin",     "npc_mme_danglars","dlg_mme_danglars_ruin"),

    # Faria's tutorials run end to end, so his five rungs read as one spine.
    ("dlg_faria_teach_2",     "npc_faria",       "dlg_faria_deduce"),
    ("dlg_faria_treasure",    "npc_faria",       "dlg_faria_death"),

    # Marseilles and the isle.
    ("dlg_grotto",            "npc_jacopo",      "dlg_jacopo_farewell"),
    ("dlg_wilmore_donning",   "npc_penelon",     "dlg_penelon_affair"),
    ("dlg_caderousse_diamond","npc_caderousse",  "dlg_caderousse_spending"),
    ("dlg_caderousse_diamond","npc_carconte",    "dlg_carconte_diamond"),
    ("dlg_morrel_rescue",     "npc_julie",       "dlg_julie_purse"),
    ("dlg_julie_purse",       "npc_morrel",      "dlg_morrel_toast"),
    ("dlg_julie_purse",       "npc_maximilien",  "dlg_maximilien_thanks"),

    # Rome — the rescue is the talk of the hotel.
    ("dlg_albert_rescue",     "npc_pastrini",    "dlg_pastrini_rescue"),
    ("dlg_albert_rescue",     "npc_franz",       "dlg_franz_doubt"),
    ("dlg_albert_invitation", "npc_albert",      "dlg_albert_paris"),

    # Paris — one event, several people who now have something to say.
    ("dlg_chamber_trial",     "npc_albert",      "dlg_albert_challenge"),
    ("dlg_chamber_trial",     "npc_renaud",      "dlg_renaud_scandal"),
    ("dlg_albert_challenge",  "npc_mercedes",    "dlg_mercedes_plea"),
    ("dlg_fernand_end",       "npc_mercedes",    "dlg_mercedes_widow"),
    ("dlg_fernand_end",       "npc_haydee",      "dlg_haydee_choice"),
    ("dlg_villefort_fence",   "npc_villefort",   "dlg_villefort_rattled_talk"),
    ("dlg_telegraph_man",     "npc_debray",      "dlg_debray_telegraph"),
    ("dlg_benedetto_groom",   "npc_eugenie",     "dlg_eugenie_assessed"),
    ("dlg_poison_watch",      "npc_barrois",     "dlg_barrois_deaths"),
    ("dlg_noirtier",          "npc_valentine",   "dlg_valentine_vigil"),
]

for _src, _char, _tgt in ROUTE_LIST:
    _pin = "active_dialogue__" + _char
    _srcd = DIALOGUES[_src]
    _ends = [n for n in _srcd["nodes"] if n.get("isEnd")]
    _target_node = _ends[-1] if _ends else _srcd["nodes"][-1]
    _target_node.setdefault("onEnter", []).append(
        {"character": _char, "dialogue": _tgt, "type": "set_active_dialogue"})
    FLAG_W.setdefault(_pin, _src)
    # Clear the pin as the target ends — but NOT on a failure branch. A
    # fumbled attempt should leave the character still wanting to talk about
    # it, so you can come back; clearing there would also mean a failed roll
    # silently reorders the ladder, which is the punishment spiral the
    # validator warns about.
    _fail_nodes = set()
    for _n in DIALOGUES[_tgt]["nodes"]:
        for _ch in _n.get("choices", []):
            if "check" in _ch:
                _fail_nodes.add(_ch["check"]["onFailure"])
    for _n in DIALOGUES[_tgt]["nodes"]:
        if _n.get("isEnd") and _n["id"] not in _fail_nodes:
            _n.setdefault("onEnter", []).append({"flag": _pin, "type": "set_flag", "value": False})
    # The target's rung accepts the pin OR its own story condition.
    _cfile = FILES[f"data/characters/{_char}.json"]
    for _rung in _cfile["dialogues"]:
        if _rung["dialogue"] == _tgt:
            if "showIf" in _rung:
                _rung["showIf"] = {"of": [{"flag": _pin, "type": "flag", "value": True},
                                          _rung["showIf"]], "type": "any"}
            else:
                _rung["showIf"] = {"flag": _pin, "type": "flag", "value": True}
            FLAG_R.add(_pin)
            break


# ===================== SAVED ROUTES (tests/routes) ==========================
# Route ENTITIES are a different thing from the flow-map "routes" above: these
# are recorded, asserted playthroughs of a single dialogue. `forced` pins a
# check's outcome so the assertion is deterministic — which is exactly what an
# undirected walker cannot give you. Each one guards an invariant that would
# otherwise only break silently.

def RT(rid, dialogue, steps, assert_end, description, start=None, seed=None):
    r = {"description": description, "dialogueId": dialogue, "id": rid, "steps": steps}
    if assert_end: r["assertEnd"] = assert_end
    if start: r["startState"] = start
    if seed is not None: r["seed"] = seed
    FILES[f"tests/routes/{rid}.json"] = r

RT("rt_letter_taken", "dlg_pharaon_deck",
   [{"choiceId": "dlg_pharaon_deck_take"}],
   {"flags": {"took_letter": True}},
   "Taking Leclère's packet is what arms the whole plot. If this stops setting "
   "took_letter, Villefort's interrogation loses its honest branch and Act I "
   "quietly becomes unlosable.")

RT("rt_letter_refused", "dlg_pharaon_deck",
   [{"choiceId": "dlg_pharaon_deck_refuse"}],
   {"forbiddenFlags": ["took_letter"]},
   "Refusing the packet must leave took_letter false — that is the branch that "
   "opens the 'innocent' answer to Villefort.")

RT("rt_interrogation_failed", "dlg_villefort_interrogation",
   [{"choiceId": "dlg_villefort_interrogation_truth", "forced": "fail"}],
   {"flags": {"letter_burned": True, "condemned": True}},
   "The priced check pays its way: telling the truth badly still ends with the "
   "letter burned and Dantès condemned. If a failed roll ever leaves condemned "
   "false, the check has stopped being priced and become a wall — Act II "
   "unreachable, and nothing else would notice.",
   start={"inventory": ["item_letter_elba"], "flags": {"took_letter": True}})

RT("rt_interrogation_truth", "dlg_villefort_interrogation",
   [{"choiceId": "dlg_villefort_interrogation_truth", "forced": "pass"}],
   {"flags": {"letter_burned": True, "condemned": True}},
   "Passing changes the route through the scene but not its destination. Both "
   "branches must converge on the cell; Villefort burns the letter either way, "
   "because his own father is the addressee.",
   start={"inventory": ["item_letter_elba"], "flags": {"took_letter": True}})

RT("rt_faria_blind_deduction", "dlg_faria_deduce",
   [{"choiceId": "dlg_faria_deduce_blind", "forced": "fail"}],
   {"flags": {"knows_betrayers": True}},
   "Faria reaches the answer even when Dantès cannot. Failing the deduction "
   "routes through 'led' and still arrives at the three names — the education "
   "quest must not be gated on the player being clever.")

RT("rt_grotto_fumbled", "dlg_grotto",
   [{"choiceId": "dlg_grotto_dig", "forced": "fail"}],
   {},
   "The treasure is not a skill gate. Both branches of the dig arrive at the "
   "gold; a fumbled roll costs nothing, because everything after Act III "
   "assumes the fortune exists.",
   start={"flags": {"knows_treasure": True}})

RT("rt_diamond_given", "dlg_caderousse_diamond",
   [{"choiceId": "dlg_caderousse_diamond_probe", "forced": "pass"},
    {"choiceId": "dlg_caderousse_diamond_give"}],
   {"flags": {"heard_inn_tale": True, "gave_diamond": True}},
   "The inn scene must both inform and offer the choice: hearing the tale sets "
   "heard_inn_tale, and the stone can then be given. Losing the second step "
   "would collapse the moral test into an exposition dump.",
   start={"inventory": ["item_diamond"], "flags": {"identity_busoni": True}})

RT("rt_diamond_withheld", "dlg_caderousse_diamond",
   [{"choiceId": "dlg_caderousse_diamond_probe", "forced": "pass"},
    {"choiceId": "dlg_caderousse_diamond_hold"}],
   {"flags": {"heard_inn_tale": True}, "forbiddenFlags": ["gave_diamond"]},
   "Withholding is a real option, not a dead end — the quest still completes "
   "on heard_inn_tale. Only the neutral outcome differs.",
   start={"inventory": ["item_diamond"], "flags": {"identity_busoni": True}})

RT("rt_mercedes_spares_the_son", "dlg_mercedes_plea",
   [{"choiceId": "dlg_mercedes_plea_spare"}],
   {"flags": {"duel_spared": True}, "forbiddenFlags": ["duel_hard"]},
   "Mercédès can only reach Edmond through what she has earned: the sparing "
   "choice is gated on relationship >= 2. If that gate ever admits a stranger, "
   "the mercy ending stops costing anything.",
   start={"relationships": {"npc_mercedes": 2}, "flags": {"duel_pending": True}})

RT("rt_vigil_saves_valentine", "dlg_valentine_vigil",
   [{"choiceId": "dlg_valentine_vigil_feign", "forced": "pass"}],
   {"flags": {"valentine_saved": True}},
   "The one life kept out of the ledger. Wait and Hope is unreachable without "
   "this flag, so a change that breaks the vigil silently removes the good "
   "ending rather than failing loudly.",
   start={"flags": {"noirtier_ally": True, "vowed_valentine": True,
                    "valentine_trusts": True, "household_dying": True}})

RT("rt_vigil_fumbled", "dlg_valentine_vigil",
   [{"choiceId": "dlg_valentine_vigil_feign", "forced": "fail"}],
   {"forbiddenFlags": ["valentine_saved"]},
   "A fumbled vigil must NOT count as a rescue. This is the guard on the "
   "punishment-spiral fix: failure costs suspicion and leaves the attempt open, "
   "rather than paying out the reward flag.",
   start={"flags": {"noirtier_ally": True, "vowed_valentine": True,
                    "valentine_trusts": True, "household_dying": True}})

RT("rt_larder_mercy", "dlg_vampa_larder",
   [{"choiceId": "dlg_vampa_larder_spare"}],
   {"flags": {"danglars_spared": True}},
   "Leaving one man alive to be old. The mercy quest turns on this, and it is "
   "the difference between Wait and Hope and The Avenger.",
   start={"flags": {"danglars_ruined": True}})

# --- Cross-dialogue routes: the act transitions that stranded content -------
# These walk THROUGH a cutscene into the next scene. Each guards a transition
# that broke silently during authoring — the validator was green while Act III
# was unreachable, because reachability is not something it checks.

RT("rt_escape_into_the_sea", "dlg_shroud",
   [{"choiceId": "dlg_shroud_swap", "forced": "pass"},
    {"cutscene": "cs_escape_shroud"},
    {"choiceId": "dlg_jacopo_rescue_story", "forced": "pass"}],
   {"flags": {"escaped": True, "aboard_amelie": True}, "pendingCutscene": None},
   "The whole of Act III hangs on this three-part transition: the shroud, the "
   "cutscene, and being pulled aboard the Jeune-Amélie. If the cutscene loses "
   "its entersDialogue the chain breaks here and Monte Cristo becomes "
   "unreachable — with every individual dialogue still validating perfectly.",
   start={"inventory": ["item_file"], "flags": {"faria_dead": True}})

RT("rt_rome_into_paris", "dlg_albert_invitation",
   [{"choiceId": "dlg_albert_invitation_accept"},
    {"cutscene": "cs_paris_entrance"}],
   {"flags": {"paris_invitation": True, "identity_count": True},
    "pendingCutscene": None},
   "Rome hands off to Paris through cs_paris_entrance. That cutscene shipped "
   "with no entersDialogue at first, so the Count arrived nowhere and all four "
   "Paris quests sat behind a door that never opened.",
   start={"flags": {"albert_saved": True}})

RT("rt_the_letter", "dlg_wait_and_hope",
   [{"advance": 1}],
   {"flags": {"story_closed": True}},
   "The finale is a listen-only beat reached by `next`, not a choice. A runtime "
   "that treats a choiceless node as the end of the conversation never fires "
   "story_closed, and both good endings quietly become unreachable — which is "
   "exactly the bug that hid the lantern in mistfall-inn.",
   start={"flags": {"villefort_done": True, "fernand_ruined": True,
                    "danglars_ruined": True}})

RT("rt_morrel_debts_bought", "dlg_morrel_rescue",
   [{"choiceId": "dlg_morrel_rescue_buy"}],
   {"flags": {"morrel_bought": True}},
   "Buying the house's debts is step one of the mercy thread, and it is only "
   "reachable if Act III can return to Marseilles. The exit that makes this "
   "possible was missing for a while; see tools/check_reachability.py, which "
   "guards the geography this route assumes.",
   start={"inventory": ["item_treasure"], "flags": {"identity_wilmore": True}})

RT("rt_purse_saves_the_house", "dlg_julie_purse",
   [{"choiceId": "dlg_julie_purse_send"}],
   {"flags": {"morrel_saved": True}},
   "The red purse on the mantel. morrel_saved gates Maximilien's vow, which "
   "gates the vigil, which gates Wait and Hope — the longest causal chain in "
   "the project, and it starts here.",
   start={"inventory": ["item_red_purse"], "flags": {"morrel_bought": True}})

RT("rt_larder_relents", "dlg_vampa_larder",
   [{"choiceId": "dlg_vampa_larder_starve", "forced": "fail"}],
   {"flags": {"danglars_spared": True}},
   "Even choosing to starve him relents in the end — both branches set "
   "danglars_spared, because the novel's point is that vengeance runs out "
   "before the prisoner does.",
   start={"flags": {"danglars_ruined": True}})

# ===================== VARIABLES + SELF-LINT + WRITE =======================
# A marker exists to be depended upon; leaf quests should not mint state
# nobody reads.
_needed = {fl for fl in FLAG_R if fl.endswith("_complete")}
for _rel, _obj in FILES.items():
    if not _rel.startswith("data/quests/"):
        continue
    for _oc in _obj.get("outcomes", []):
        _effs = _oc.get("effects")
        if not _effs:
            continue
        _keep = []
        for _e in _effs:
            if (_e["type"] == "set_flag" and _e["flag"].endswith("_complete")
                    and _e["flag"] not in _needed):
                FLAG_W.pop(_e["flag"], None)
            else:
                _keep.append(_e)
        if _keep:
            _oc["effects"] = _keep
        else:
            _oc.pop("effects", None)

problems = []
for flag in sorted(FLAG_R - set(FLAG_W)):
    problems.append(f"flag READ but never WRITTEN: {flag}")
for flag in sorted(set(FLAG_W) - FLAG_R):
    problems.append(f"flag WRITTEN but never READ: {flag} (at {FLAG_W[flag]})")
for item in sorted(ITEM_R - ITEM_G):
    problems.append(f"item READ but never GIVEN: {item}")
for item in sorted(ITEM_G - ITEM_R):
    problems.append(f"item GIVEN but never READ: {item}")
for did, d in DIALOGUES.items():
    ids = {n["id"] for n in d["nodes"]}
    for n in d["nodes"]:
        for tgt in ([n.get("next")] if n.get("next") else []):
            if tgt not in ids: problems.append(f"{did}: next -> missing {tgt}")
        for ch in n.get("choices", []):
            for tgt in [ch.get("goto"), ch.get("check", {}).get("onSuccess"),
                        ch.get("check", {}).get("onFailure")]:
                if tgt and tgt not in ids: problems.append(f"{did}: -> missing {tgt}")
    if d["entry"] not in ids: problems.append(f"{did}: entry missing")
for rel_path, obj in list(FILES.items()):
    if rel_path.startswith("data/characters/"):
        for rung in obj["dialogues"]:
            if rung["dialogue"] not in DIALOGUES:
                problems.append(f"{obj['id']}: ladder -> missing {rung['dialogue']}")
    if rel_path.startswith("data/locations/"):
        for it in obj["interactables"]:
            if it["kind"] == "object" and it["dialogue"] not in DIALOGUES:
                problems.append(f"{obj['id']}: object -> missing {it['dialogue']}")
if problems:
    print("SELF-LINT FAILURES:"); [print("  -", p) for p in problems]; sys.exit(1)

variables = [{"default": False, "description": f"First written at '{FLAG_W[fl]}'.",
              "id": fl, "kind": "flag"} for fl in sorted(FLAG_W)]
variables += [
    {"default": 0, "description": "Years gone in the Château d'If.", "id": "years", "kind": "counter"},
    {"default": 0, "description": "How much the world has noticed you looking.", "id": "suspicion", "kind": "counter"},
]
FILES["data/variables.json"] = {"variables": variables}

FILES_LORE = """# A scale fixture shaped like The Count of Monte Cristo

The QUEST STRUCTURE, gates, ladders and identities follow Dumas's novel; the
node text is drawn from the 1846 English translation (US public domain, via
Project Gutenberg), scoped to the act each scene belongs to, but recombined —
it will not read as continuous prose. This is a demonstration project for
tooling at scale, not an adaptation. Read `mistfall-inn` to learn the format.
"""
write_all()
(OUT / "lore").mkdir(exist_ok=True)
(OUT / "lore" / "monte-cristo.md").write_text(FILES_LORE, encoding="utf-8")
for name, body in LORE_EXTRA.items():
    (OUT / "lore" / name).write_text(body, encoding="utf-8")
print(f"dialogues={len(DIALOGUES)} nodes={sum(len(d['nodes']) for d in DIALOGUES.values())} "
      f"flags={len(FLAG_W)} files={len(FILES)}")

