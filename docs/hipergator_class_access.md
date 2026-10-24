# HiPerGator Access Guide (Course / This Project)

How to get onto UF HiPerGator, reach a **compute or development node** for this class, and navigate to your course Blue space.

Replace placeholders with your real values (from UFIT-RC / course staff — do not invent them):

| Placeholder | Meaning |
|-------------|---------|
| `<gatorlink>` | Your GatorLink username |
| `<COURSE_GROUP>` | Course SLURM account / group (orientation example `pre1234` is **not** your real group) |

---

## 1. What you can and cannot SSH to

| Target | Allowed? | How |
|--------|----------|-----|
| Login gateway | Yes | `ssh <gatorlink>@hpg.rc.ufl.edu` |
| Compute nodes (by hostname) | **No** | Direct interactive SSH to compute nodes is **prohibited** |
| Dev / compute shell | Yes | After login, start a **SLURM interactive session** (`srun`, `sruni`, `srundev`) |

You always SSH to the **login** node first. Login nodes are for editing files, submitting jobs, and checking status — **not** for running MCMC, smoke tests, or heavy Python.

Official policy summary: [HiPerGator usage policies](https://it.ufl.edu/rc/documentation/policies/hipergator-usage-policies/) · SSH: [Connecting with SSH](https://docs.rc.ufl.edu/interfaces/terminal/).

---

## 2. Step-by-step: SSH into HiPerGator

### From your laptop (Windows PowerShell, macOS Terminal, or Linux)

```bash
ssh <gatorlink>@hpg.rc.ufl.edu
```

1. Enter your GatorLink password when prompted.
2. Complete **Duo MFA** (push / passcode).
3. You land on a **login** node. Prompt looks something like:
   ```text
   [<gatorlink>@loginN ~]$
   ```

Optional: if you use SSH keys on port 2222 per UF docs, follow the current [SSH Connections](https://docs.rc.ufl.edu/interfaces/terminal/) page. Default for most users is port 22 and password + Duo.

**Do not** start long MCMC runs or `scripts/net_smoke` here.

---

## 3. Get onto a compute / development node (the “access compute” step)

Still connected via SSH to the login node, request an interactive SLURM job. That places your shell **on** a compute or development node for the duration of the allocation.

### Recommended pattern for this class

Always include your course account and QOS:

```bash
srun --account=<COURSE_GROUP> --qos=<COURSE_GROUP> \
  --ntasks=1 --cpus-per-task=1 --mem=4gb --time=01:00:00 \
  --pty bash -i
```

Adjust CPUs, memory, and time as needed. When the job starts, your prompt changes to a **compute/dev hostname** (not `loginN`). You are now “on” the compute side without having SSHed to that hostname directly.

### UF helper commands (if available on your account)

| Command | Typical use |
|---------|-------------|
| `sruni ...` | Interactive session on a **compute** node |
| `srundev ...` | Interactive session on a **development** node (good for edit/build/test) |
| `srungui ...` | GUI-oriented interactive session |

Examples (still add `--account` / `--qos` if the helper does not inject them for you — check `sruni --help` / course notes):

```bash
# Development node (preferred for coding / short tests)
srundev --account=<COURSE_GROUP> --qos=<COURSE_GROUP> -t 2:00:00

# Compute node interactive
sruni --account=<COURSE_GROUP> --qos=<COURSE_GROUP> -c 2 --mem=8gb -t 60
```

Generic SLURM interactive form from UF docs:

```bash
srun --ntasks=1 --cpus-per-task=2 --mem=2gb -t 90 --pty bash -i
```

For this course, **prefer** the version that includes `--account=<COURSE_GROUP>` and `--qos=<COURSE_GROUP>`.

### Leaving the interactive session

```bash
exit
```

You return to the login node. The allocation ends.

---

## 4. Paths that matter for this class

| Path | Purpose |
|------|---------|
| `/home/<gatorlink>` | Small home (~40 GB). Scripts, configs, git clones OK. **Not** for heavy job I/O. |
| `/blue/<COURSE_GROUP>/<gatorlink>` | **Class Blue space** — run jobs and write outputs here |
| `/orange/...` | Archive; do not use for active HPC I/O |

Orientation expectation:

```text
mkdir -p /blue/<COURSE_GROUP>/<gatorlink>
# and for this project, e.g.:
mkdir -p /blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime
```

Every `#SBATCH` script for class work should include:

```bash
#SBATCH --account=<COURSE_GROUP>
#SBATCH --qos=<COURSE_GROUP>
```

Burst QOS (if your course provides it) is often `--qos=<COURSE_GROUP>-b`.

---

## 5. Navigate to your class Blue directory

### After SSH (on login or after `srun`)

```bash
# Go to your class Blue folder
cd /blue/<COURSE_GROUP>/<gatorlink>

# Confirm where you are
pwd
ls

# Project runtime folder (create if missing)
mkdir -p mcmc_runtime
cd mcmc_runtime
```

### Shortcuts

```bash
# Home
cd ~
# or
cd /home/<gatorlink>

# Class Blue root
cd /blue/<COURSE_GROUP>/<gatorlink>

# If you already exported a variable in ~/.bashrc:
# export HPG_CLASS_BLUE=/blue/<COURSE_GROUP>/<gatorlink>
# then:
# cd "$HPG_CLASS_BLUE"
```

### Find your group name if you forgot it

On HiPerGator (after login):

```bash
showAssoc          # SLURM account associations (if UFRC tools loaded)
groups             # Unix groups — course group often appears here
ls /blue           # list Blue projects you can see (may be long)
```

Use the course Slack / Canvas / RC orientation sheet for the official `<COURSE_GROUP>` string.

---

## 6. Batch jobs vs interactive (when to use which)

| Mode | Command | Use for |
|------|---------|---------|
| Interactive | `srun` / `sruni` / `srundev` | Debugging, editing, short smoke tests by hand |
| Batch | `sbatch slurm/....sh` | Reproducible runs, net smoke scripts, overnight work |

Example batch submit (from a clone that contains this repo, preferably under Blue or with outputs on Blue):

```bash
cd /blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime
# edit SLURM script placeholders first
sbatch /path/to/repo/slurm/net_smoke_same_node.sh
squeue -u <gatorlink>
```

See also:

- `docs/hipergator_outbound_connect_smoke_test.md` — TCP smoke test (coordinator listens, worker dials)
- `scripts/net_smoke/` — tiny HELLO/ACK scripts
- `slurm/net_smoke_same_node.sh`, `slurm/net_smoke_two_nodes.sh`

---

## 7. Network mode reminder (this project)

Platform decision for replica workers:

- **Coordinator listens**
- **Workers connect outbound**

Do **not** design HiPerGator jobs around “SSH into each compute node and start a listening worker from your laptop.” Stay inside one SLURM allocation and dial the coordinator host from workers.

---

## 8. Quick checklist

- [ ] `ssh <gatorlink>@hpg.rc.ufl.edu` + Duo
- [ ] Know `<COURSE_GROUP>` from course/RC materials
- [ ] `mkdir -p /blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime`
- [ ] Interactive work: `srun`/`srundev`/`sruni` with `--account` and `--qos`
- [ ] Job I/O under `/blue/<COURSE_GROUP>/<gatorlink>/...`
- [ ] Never run project compute on the login node
- [ ] Never rely on direct SSH to compute hostnames

---

## 9. How to get to “your class” when you’re done connecting

Once logged in (and preferably after starting an interactive session if you will run code):

```bash
cd /blue/<COURSE_GROUP>/<gatorlink>
pwd
ls
```

That directory **is** your class working area on HiPerGator Blue. Put clones, smoke-test logs, and job outputs under it (e.g. `mcmc_runtime/`).

If you only need to edit small files and submit `sbatch`, you can `cd` there on the **login** node; if you will run Python/smoke tests interactively, `cd` there **after** `srun`/`srundev` so the work runs on a compute/dev node.
