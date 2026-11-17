# Agent handoff: Final project milestone — draft poster

**Owner:** Justin Sobayo  
**Course / cluster:** UF HiPerGator `gly4930`  
**Repo:** `Distributed-MCMC-State-Exchange-Runtime`  
**Date:** 2026-11-11  
**Assignment:** Final project milestone — draft poster for peer review  

Give this file to another agent and ask them to **produce a draft academic poster** (content + layout) for peer review. Do **not** invent finished science claims beyond what the archived runs support.

---

## 1. Assignment requirements (must hit)

Source: course “Final project milestone assignment” (poster draft for peer review).

| Requirement | Detail |
|-------------|--------|
| Deliverable | Draft poster for peer review |
| Content | Updated figures, new draft figures, title, name, headings, draft text, placeholders for missing figures/schematics |
| Format | **Landscape**, ~**48" wide × 36" tall** |
| Goal | Show clear progress toward completion (not a polished final) |
| Rubric — Progress to completeness (2 pts) | Most sections present: title, intro, methods, results, conclusion + preliminary content |
| Rubric — Design (1 pt) | Organized layout, visual hierarchy, readable fonts/colors, meaningful figure placement |
| Rubric — Peer review (2 pts) | Justin still does peer review of others; poster agent need not write those reviews |

Example poster style in the assignment (Mackie et al. Antarctic calving): clean sections, large figures with short captions, QR/sidebar optional. Match **structure/clarity**, not their science topic.

---

## 2. Project one-liner (use this framing)

**Distributed MCMC state-exchange runtime** for parallel tempering (PT) on glacier bed / topography inverse problems (Stancomb Wills CRF via Niya’s `gstatsMCMC`), with a Python coordinator + replica workers now, and a future C++/multi-node/GPU runtime.

**Research question for the poster:**  
Can temperature-exchange parallel tempering improve mixing / exploration for Stancomb bed inference under an **equal-resource** baseline, and what runtime does that require?

**Honest status today:**  
2-replica swap machinery is validated; a useful multi-rung ladder (4+) is the next science step; GPU/C++ are scale-up, not required for the draft poster story.

---

## 3. What is already true (safe to put on the poster)

### Engineering
- Coordinator **listens**; workers **dial out** (HiPerGator-friendly).
- Python two-replica PT stack works on HPG compute nodes (Stancomb CPU).
- N-replica coordinator + `neighbor_odd_even` pairing implemented (ready for 4-replica campaigns).
- Config-driven matched experiments: dual-cold vs PT at same `rounds` × `batch_n_iterations`.

### Science / experiments (Stancomb)
| Run | Temps | Exchange | Rounds | Key result | Local archive / figure |
|-----|-------|----------|--------|------------|------------------------|
| Dual-cold baseline | `[1,1]` | OFF | 200 | Energy ~186k→142k; `a_local`~0.58 | `figures/dual_cold_stancomb_r200/` |
| PT | `[1, 1.5]` | ON | 200 | `a_swap=0.01` — ladder too sparse | `figures/energy_trace_stancomb_r200/` |
| PT | `[1, 1.2]` | ON | 200 | Still ~`a_swap=0.01` | HPG `results/..._T1.2` |
| PT swap-health | `[1, 1.01]` | ON | 200 | Late accepts only; `a_swap=0.075` | HPG `..._T1.01` |
| PT swap-health | `[1, 1.01]` | ON | 600 | **`a_swap≈0.51`**; post≥180 **`≈0.71`**; many cold-label flips; local accept unchanged | `figures/pt_stancomb_r600_T1.01/` + `benchmarks/two_replica_stancomb_pt_r600_T1.01/` |
| Dual-cold matched | `[1,1]` | OFF | 600 | Control for PT r600 (plot if not yet) | `benchmarks/two_replica_stancomb_baseline_cold_r600/` (scp’d) |

**Literature-backed lesson (put in Methods/Results):**  
Neighbor swap acceptance should be ~20–40% (Kone & Kofke / Atchadé; Vousden–Farr–Mandel adaptive ladders). With **2** replicas, a hot end hot enough to explore kills swaps; temps close enough to swap barely temper. **More rungs** are required for useful PT.

**Do not claim on the draft poster:**
- That PT already improves Stancomb bed quality vs dual-cold in a decisive way.
- That `a_swap` alone proves scientific usefulness.
- That GPU/C++ results exist (they don’t yet).

---

## 4. Suggested poster outline (48×36 landscape)

Working title ideas (agent may refine):
- “Equal-resource parallel tempering for distributed Stancomb bed MCMC”
- “From dead ladders to swap health: building a PT runtime for glacier inverse problems”

**Author line:** Justin Sobayo (+ advisors/collaborators if Justin supplies names)

| Panel | Content |
|-------|---------|
| **Intro / Motivation** | Glacier bed inference is multimodal / expensive; PT can help mixing; need distributed runtime on HPG |
| **Methods — Runtime** | Schematic: coordinator listen + N workers dial; batch barrier → neighbor swap → set T. Placeholder OK if no polished diagram yet |
| **Methods — Experiments** | Stancomb CRF; matched budgets; dual-cold vs PT; temperature ladder diagnostics (`a_swap`, cold flips, `a_local`) |
| **Results — Dead ladder** | Energy-trace or table: T=1.5 / 1.2 → `a_swap≈0.01` |
| **Results — Swap health** | PT r600 T=1.01 figure (4-panel); highlight post-burn-in swaps + cold flips; note `a_local` unchanged |
| **Results — Control** | Dual-cold r600 (generate figure if missing) vs PT cold energy |
| **Next steps** | 4-replica dense ladder `[1, 1.01, 1.025, 1.05]` (T1.35 froze); then GPU; C++ runtime |
| **Conclusion** | Swap machinery works; useful PT needs N>2; equal-resource baselines are mandatory |

Placeholders (boxes with captions) for: architecture schematic, 4-replica results (campaign may still be running), bed map visuals.

---

## 5. Figures and paths to reuse

Already generated (prefer these over reinventing):

```text
figures/dual_cold_stancomb_r200/dual_cold_stancomb_r200_trace.png
figures/energy_trace_stancomb_r200/energy_trace_stancomb_r200.png
figures/pt_stancomb_r600_T1.01/pt_stancomb_r600_T1.01_trace.png
```

Data archives:

```text
benchmarks/two_replica_stancomb_pt_r600_T1.01/
benchmarks/two_replica_stancomb_baseline_cold_r600/
```

Plot scripts:

```text
MCMC_implementation/scripts/plot_dual_cold_baseline.py
MCMC_implementation/scripts/plot_pt_run.py
MCMC_implementation/scripts/plot_energy_trace.py
```

If dual-cold r600 figure is missing, run:

```bash
python MCMC_implementation/scripts/plot_dual_cold_baseline.py \
  --run-dir benchmarks/two_replica_stancomb_baseline_cold_r600 \
  --output-dir figures/dual_cold_stancomb_r600 \
  --stem dual_cold_stancomb_r600
```

Optional matched energy-trace (update defaults or pass dirs for r600 PT vs dual-cold).

HPG long campaign (may be in flight while poster is drafted):

```text
results/four_replica_stancomb_baseline_cold_r2000_T1.05match
results/four_replica_stancomb_pt_r2000_T1.05
# prior (dead ladder): …_pt_r2000_T1.35  a_swap≈0.008
```

Use as **“in progress / forthcoming”** placeholders until data is local.

---

## 6. Key docs for deeper context

| Doc | Why |
|-----|-----|
| `notes/decisions/pt_next_steps_ladder_and_gpu.md` | Locked next-step plan |
| `docs/pt_temperature_energy_investigation.md` | Temperature in Metropolis accept |
| `docs/replica_worker_implementation_plan.md` | Worker/coordinator design |
| `notes/decisions/networking_stack_and_application_protocol.md` | Listen/dial protocol |
| `MCMC_implementation/configs/*stancomb*.yaml` | Exact experiment settings |

---

## 7. Deliverables the poster agent should produce

1. **Draft poster file** in an editable form (prefer PowerPoint / Google Slides / PDF export). Landscape 48×36.
2. Short **figure list** mapping each poster panel → file path or “placeholder”.
3. **Draft text** for Intro / Methods / Results / Conclusions (bullet-level OK).
4. List of **missing assets** Justin still needs (schematic, 4-replica plots, advisor names, QR, logos).

Optional: a one-page `docs/poster_draft_notes.md` with the text + figure map if the binary poster isn’t feasible in-agent — but aim for an actual slide/PDF layout if tools allow.

---

## 8. Design constraints

- Readable from ~5–6 feet: large title, short captions, few walls of text.
- Prefer existing project figures; don’t invent fake curves.
- Avoid purple-on-white AI-default poster kits; keep a simple academic look (UF branding only if Justin provides logos).
- Clearly label **draft / preliminary** where results are incomplete.
- Distinguish **runtime contribution** vs **PT diagnostic results**.

---

## 9. What Justin is doing in parallel (do not block on)

- HPG `srun` with 4 CPUs / 4h running `run_stancomb_long_campaign.sh` (4-replica baseline r2000 → PT r2000).
- Grocery / AFK — poster agent should proceed with **existing** 2-replica figures + placeholders for 4-replica.

---

## 10. Success check for this milestone

- [ ] Landscape draft poster exists with title, name, intro, methods, results, conclusion
- [ ] ≥2 real figures embedded (dual-cold and/or PT r600 and/or energy-trace)
- [ ] Placeholders for schematic + forthcoming 4-replica results
- [ ] Text does not overclaim PT scientific win
- [ ] Looks organized enough for peer review (rubric “progress toward design”)
