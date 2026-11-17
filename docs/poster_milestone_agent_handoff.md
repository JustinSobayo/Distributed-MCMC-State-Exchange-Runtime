# Agent handoff: Final project milestone — draft poster

**Owner:** Justin Sobayo  
**Course / cluster:** UF HiPerGator `gly4930`  
**Repo:** `Distributed-MCMC-State-Exchange-Runtime` (branch `dev`)  
**Date:** 2026-11-17  
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

**Honest status (2026-11-17):**  
- 2-replica swap machinery validated (`[1, 1.01]` r600).  
- N-replica (`neighbor_odd_even`) coordinator proven on HPG.  
- Sparse 4-rung ladder **froze**; dense cold-end ladder **restored mixing**.  
- **No decisive PT energy win** vs matched multi-cold yet — say that clearly.  
- GPU/C++ are scale-up, not required for the draft poster story.

---

## 3. What is already true (safe to put on the poster)

### Engineering
- Coordinator **listens**; workers **dial out** (HiPerGator-friendly).
- Python N-replica PT stack works on HPG compute nodes (Stancomb CPU).
- Config-driven matched experiments: N-cold baseline vs PT at same `rounds` × `batch_n_iterations`.
- Campaign script: `MCMC_implementation/scripts/run_stancomb_long_campaign.sh`  
  Env on HPG: `conda activate /blue/gly4930/justinsobayo/mcmc_runtime/envs/gstatsMCMC`  
  (must be on a **compute** node via `srun`, not login).

### Science / experiments (Stancomb)

| Run | Temps | Exchange | Rounds | Key result | Local archive / figure |
|-----|-------|----------|--------|------------|------------------------|
| Dual-cold baseline | `[1,1]` | OFF | 200 | Energy ~186k→142k; `a_local`~0.58 | `figures/dual_cold_stancomb_r200/` |
| PT | `[1, 1.5]` | ON | 200 | `a_swap=0.01` — ladder too sparse | `figures/energy_trace_stancomb_r200/` |
| PT | `[1, 1.2]` | ON | 200 | Still ~`a_swap=0.01` | HPG `results/..._T1.2` |
| PT swap-health | `[1, 1.01]` | ON | 600 | **`a_swap≈0.51`**; post≥180 **`≈0.71`**; many cold-label flips; `a_local` unchanged | `figures/pt_stancomb_r600_T1.01/` + `benchmarks/two_replica_stancomb_pt_r600_T1.01/` |
| Dual-cold matched | `[1,1]` | OFF | 600 | Control for PT r600 | `benchmarks/two_replica_stancomb_baseline_cold_r600/` |
| **4× cold baseline** | `[1,1,1,1]` | OFF | 2000 | E ~185k→~111k; `a_local`~0.58 | `figures/four_replica_stancomb_r2000_T1.05/` (baseline panel) + `benchmarks/four_replica_stancomb_baseline_cold_r2000_T1.05match/` |
| **4-replica PT (dead)** | `[1, 1.05, 1.15, 1.35]` | ON | 2000 | **`a_swap≈0.008`**; T freezes ~r350; post-burn-in swaps ≈0 | `figures/four_replica_stancomb_r2000_T1.35/` + `benchmarks/four_replica_stancomb_pt_r2000_T1.35/` |
| **4-replica PT (dense)** | `[1, 1.01, 1.025, 1.05]` | ON | 2000 | **`a_swap≈0.165`** (496/3000); edges 1–2 & 2–3 ~0.20; cold 0–1 ~0.10 (post-burnin ~0.056); T mixing active; E_cold 185k→**110.8k** vs baseline best **~110.7k** | `figures/four_replica_stancomb_r2000_T1.05/` + `benchmarks/four_replica_stancomb_pt_r2000_T1.05/` |

**Literature-backed lesson (Methods/Results):**  
Neighbor swap acceptance should be ~20–40% (Kone & Kofke / Atchadé; Vousden–Farr–Mandel). With **2** replicas, a hot end hot enough to explore kills swaps. **More rungs + denser cold spacing** are required. T1.35 vs T1.05 is the poster’s before/after ladder story.

**Do not claim on the draft poster:**
- That PT already improves Stancomb bed quality / final energy vs matched multi-cold in a decisive way (T1.05 cold ≈ baseline).
- That headline `a_swap` alone proves scientific usefulness (use per-edge rates + cold flips).
- That GPU/C++ results exist (they don’t yet).

---

## 4. Suggested poster outline (48×36 landscape)

Working title ideas (agent may refine):
- “Equal-resource parallel tempering for distributed Stancomb bed MCMC”
- “From dead ladders to swap health: a distributed PT runtime for glacier inverse problems”

**Author line:** Justin Sobayo (+ advisors/collaborators if Justin supplies names)

| Panel | Content |
|-------|---------|
| **Intro / Motivation** | Glacier bed inference multimodal / expensive; PT can help mixing; need distributed runtime on HPG |
| **Methods — Runtime** | Schematic: coordinator listen + N workers dial; batch barrier → neighbor odd/even swap → set T. Placeholder OK if no polished diagram |
| **Methods — Experiments** | Stancomb CRF; matched budgets; dual-cold / N-cold vs PT; diagnostics (`a_swap` by edge, cold flips, `a_local`) |
| **Results — Dead ladder** | 2-replica T=1.5/1.2 **or** 4-replica T1.35: `a_swap≈0.01` / freeze |
| **Results — Swap health (2-rep)** | PT r600 T=1.01 figure; post-burn-in swaps + cold flips; `a_local` unchanged |
| **Results — 4-replica ladder** | Prefer **T1.05 comparison** figure; contrast with T1.35 if space; note mid/hot edges ~0.2, cold edge weak late |
| **Results — Equal-resource** | PT cold E ≈ 4×T=1 baseline — no energy win yet; honest |
| **Next steps** | Tighten cold `0–1` spacing / adaptive ladder; GPU scale-up; C++ runtime |
| **Conclusion** | Runtime + swap machinery work; dense N>2 ladders restore mixing; usefulness ≠ swap rate alone |

---

## 5. Figures and paths to reuse (prefer these)

**Primary (use on poster):**

```text
figures/pt_stancomb_r600_T1.01/pt_stancomb_r600_T1.01_trace.png
figures/four_replica_stancomb_r2000_T1.05/four_replica_stancomb_r2000_T1.05_comparison.png
figures/four_replica_stancomb_r2000_T1.05/four_replica_stancomb_r2000_T1.05_pt_trace.png
figures/four_replica_stancomb_r2000_T1.35/four_replica_stancomb_r2000_T1.35_comparison.png   # dead ladder contrast
figures/dual_cold_stancomb_r200/dual_cold_stancomb_r200_trace.png
figures/energy_trace_stancomb_r200/energy_trace_stancomb_r200.png
```

**Data archives:**

```text
benchmarks/two_replica_stancomb_pt_r600_T1.01/
benchmarks/two_replica_stancomb_baseline_cold_r600/
benchmarks/four_replica_stancomb_baseline_cold_r2000_T1.05match/
benchmarks/four_replica_stancomb_pt_r2000_T1.05/
benchmarks/four_replica_stancomb_pt_r2000_T1.35/
```

**Plot scripts:**

```text
MCMC_implementation/scripts/plot_dual_cold_baseline.py
MCMC_implementation/scripts/plot_pt_run.py
MCMC_implementation/scripts/plot_energy_trace.py
MCMC_implementation/scripts/plot_four_replica_stancomb.py
```

T1.05 summary snapshot (from `figures/.../four_replica_stancomb_r2000_T1.05_summary.json`):

- `a_swap = 0.165` (496/3000)
- by edge: `0-1: 0.099`, `1-2: 0.198`, `2-3: 0.199`
- post-burnin (≥400): `0-1: 0.056`, `1-2: 0.183`, `2-3: 0.194`
- `E_cold` 185420 → 110828; baseline ends ≈ 110733–111428

---

## 6. Key docs for deeper context

| Doc | Why |
|-----|-----|
| `notes/decisions/pt_next_steps_ladder_and_gpu.md` | Ladder → GPU plan |
| `docs/pt_temperature_energy_investigation.md` | Temperature in Metropolis accept |
| `docs/replica_worker_implementation_plan.md` | Worker/coordinator design |
| `notes/decisions/networking_stack_and_application_protocol.md` | Listen/dial protocol |
| `MCMC_implementation/configs/four_replica_stancomb_*.yaml` | Current T1.05 configs |

---

## 7. Deliverables the poster agent should produce

1. **Draft poster file** in an editable form (prefer PowerPoint / Google Slides / PDF export). Landscape 48×36.
2. Short **figure list** mapping each poster panel → file path or “placeholder”.
3. **Draft text** for Intro / Methods / Results / Conclusions (bullet-level OK).
4. List of **missing assets** Justin still needs (schematic, advisor names, QR, logos, bed-map visuals).

Optional: a one-page `docs/poster_draft_notes.md` with the text + figure map if the binary poster isn’t feasible in-agent — but aim for an actual slide/PDF layout if tools allow.

---

## 8. Design constraints

- Readable from ~5–6 feet: large title, short captions, few walls of text.
- Prefer existing project figures; don’t invent fake curves.
- Avoid purple-on-white AI-default poster kits; keep a simple academic look (UF branding only if Justin provides logos).
- Label **draft / preliminary** where appropriate.
- Distinguish **runtime contribution** vs **PT diagnostic results**.
- Before/after ladder story (T1.35 freeze → T1.05 mixing) is the strongest visual narrative.

---

## 9. What Justin is doing in parallel (do not block on)

- 4-replica T1.05 campaign **complete** and plotted locally — use those figures now.
- Optional next science: denser cold `0–1` / adaptive spacing; GPU. Poster agent should **not** wait.

---

## 10. Success check for this milestone

- [ ] Landscape draft poster exists with title, name, intro, methods, results, conclusion
- [ ] ≥2 real figures embedded (include at least one of: PT r600, T1.05 comparison, T1.35 dead ladder)
- [ ] Placeholders only for schematic / bed maps / logos if missing
- [ ] Text does **not** overclaim PT scientific / energy win vs matched baseline
- [ ] Looks organized enough for peer review (rubric “progress toward design”)
