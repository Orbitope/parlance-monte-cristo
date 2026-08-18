# Monte Cristo

*The Count of Monte Cristo* as a [Parlance](https://orbitope.com/parlance-releases/)
narrative project — a large, hand-authored demonstration of the format at scale.

```
111 dialogues · 273 nodes · 31 characters · 15 locations
14 quests · 3 endings · 12 codex entries · 4 factions · 67 flags
python validate.py --strict → OK, no errors
```

## What this is, honestly

The **structure is the novel's**: the three-stage betrayal in Marseilles, the
Château d'If, Faria's education, the treasure, the identities — Abbé Busoni,
Lord Wilmore, the Count — and the three parallel revenge threads plus a mercy
thread, converging on three endings ("Wait and Hope", "The Avenger", "The
Glass of Water"). Every quest gate, dialogue ladder and item was individually
decided from Dumas.

The **prose is not readable as a story**: node text is drawn from the 1846
English translation (US public domain, Project Gutenberg ebook #1184), scoped
to the act each scene belongs to, with the famous lines pinned — *"Seek whom
the crime will profit"*, *"I arrest you in the name of the law!"* — but the
rest recombined out of order. This project exists to give narrative tooling a
realistically-shaped large project: flow maps, quest dependency graphs,
coverage reports, reference indexes. Read
[Mistfall Inn](https://github.com/Orbitope/mistfall-inn) if you want a small
example to learn the format from.

## Open it in the editor

```bash
cd <parlance>/editor
PARLANCE_ROOT=<path-to>/parlance-monte-cristo npm run dev
```

What each view has to show, and where to look:

| View | Try | Why |
|---|---|---|
| **Flow map** (Dialogues, none open) | — | 112 dialogues, 34 edges: 32 `set_active_dialogue` routes and 2 cutscene chains. Look for the hubs — `dlg_chamber_trial` and `dlg_albert_rescue` each re-point three characters at once — and follow `dlg_albert_rescue → dlg_albert_invitation → cs_paris_entrance → dlg_paris_entrance` across acts |
| **Node graph** | `dlg_caderousse_diamond` | 6 nodes: a check, a `next` chain, and a moral fork |
| | `dlg_villefort_interrogation` | Three mutually exclusive openings gated on what you carry |
| **Quest canvas** | `qst_procureur` | 7 stages, each with a journal objective |
| **Quest dependency graph** | — | 13 edges: a Marseilles-to-treasure spine, then a four-way fan-out |
| **Location map** | — | 15 locations, exits gated on items and story flags |
| **Reference index** | `identity_count` | 8 sites — the Count's arrival re-points half of Paris |
| | `valentine_saved` | 9 sites, spanning quest outcomes and endings |
| **Reports / coverage** | — | Clean: no orphan characters, unreachable nodes, or dead flags |
| **Playtest** | `dlg_faria_deduce` | Set `observation` and watch the deduction fork; seeded, so a run repeats |
| **Ladders** | `npc_villefort`, `npc_faria` | 5 rungs each |

## Testing: routes and reachability

Two guards, covering different failure modes.

**`tests/routes/` — 18 saved routes.** Recorded playthroughs with `forced`
pinning check outcomes, so assertions are deterministic. They protect
invariants that otherwise break in silence:

| Route | Guards |
|---|---|
| `rt_interrogation_failed` | The priced check pays its way — failing still ends condemned. If it ever doesn't, Act II is unreachable |
| `rt_vigil_fumbled` | A fumbled vigil must **not** count as a rescue |
| `rt_escape_into_the_sea` | The shroud → cutscene → Jeune-Amélie chain; if the cutscene loses `entersDialogue`, Act III vanishes |
| `rt_the_letter` | The finale is reached by `next`, not a choice — a runtime treating choiceless nodes as terminal never fires it |
| `rt_larder_relents` | Both branches spare Danglars; vengeance runs out before the prisoner does |

**`tools/check_reachability.py` — the check routes cannot do.** Routes walk
*dialogue* graphs; they cannot tell you whether the player can reach the room a
dialogue lives in. Delete one exit and every schema, reference and route still
passes while a third of the game becomes unvisitable.

```bash
python3 tools/check_reachability.py
```

It asserts every location can reach the start (no traps) and every dialogue is
presented by something. Removing the Act III return to Marseilles — a real bug
during authoring — reports 9 stranded locations, while `validate.py --strict`
reports no errors at all.

## Quest dependencies

The 14 quests form a real dependency graph — a Marseilles-to-treasure spine,
then a fan-out into the Paris threads:

```
qst_pharaon ─┬─ qst_conspiracy
             └─ qst_betrothal ─ qst_arrest ─ qst_tunnel ─ qst_education
                                                    └─ qst_escape ─ qst_treasure
                                                          ├─ qst_diamond
                                                          └─ qst_rome ─┬─ qst_morcerf
                                                                       ├─ qst_banker
                                                                       ├─ qst_procureur
                                                                       └─ qst_mercy
```

Worth knowing how those edges are *derived*, because it is not obvious: a
dependency exists where one quest **writes** a flag (via `stage.onComplete` or
`outcome.effects`) that a later quest's `availableWhen` **needs**. Flags written
by dialogue `onEnter` are invisible to that derivation. So each quest emits a
`{quest}_complete` marker from its terminal outcome, and downstream quests
depend on the marker. Outcome `reachedWhen` conditions deliberately stay on
dialogue-written flags, so endings still resolve in runtimes that do not
implement `resolveQuests`.

## The part worth studying: ladders

Characters carry ordered dialogue ladders — first rung whose condition passes
wins — so the same person says different things as the world moves:

| Villefort's ladder | wins when |
|---|---|
| the garden, digging | `villefort_unmasked` |
| a man checking the locks | `villefort_rattled` |
| two men measuring each other | `identity_count` |
| the interrogation | `arrested` |
| the procureur is engaged | *(always)* |

Caderousse tells a priest what he would never tell the Count. Mercédès has
four states across twenty-three years. The salon gossips (Debray,
Château-Renaud) react to the telegraph fraud and the Morcerf scandal without
ever advancing the plot — gossip observes, effect-free, so it re-visits safely.

## Regenerate

`data/` and `lore/` are generated by [`tools/skeleton.py`](tools/skeleton.py)
— which is the *source*, not a generator in the mechanical sense: every gate
and rung is hand-written in it. The build is deterministic and byte-identical:

```bash
python3 tools/skeleton.py .
```

`tools/build_corpus.py` re-extracts the text pools from Gutenberg if you want
to change the extraction; the pools and the novel text ship in `tools/` so the
default build needs no network.

## Provenance & licence

- Text: the 1846 English translation of *Le Comte de Monte-Cristo*, US public
  domain, via the verbatim Project Gutenberg file in `tools/mc.txt`.
- Everything else (structure, tooling, this file): MIT — see [LICENSE](LICENSE).
- Validated with Parlance's validator (18 check families) under `--strict`;
  playable end-to-end via [parlance-gdscript](https://github.com/Orbitope/parlance-gdscript).
