# BreakingWeb — Human Recording Setup

> For P1 / P2 / P3 / P4 (full-load) and D1 / D2 / D3 / D4 (duplicate).

**Two docs:**
- **This file (README.md)** — install + launch + submit traces. The *how-to-run* guide.
- **[GUIDELINES.md](./GUIDELINES.md)** — what counts as a valid recording, what you may / may not do, how to report bugs. The *how-to-behave* guide. **Read it before your first recording.**

You'll record a fixed set of tasks under two conditions (`clean` + `intervention`), each twice (`cold` → `warm`), on your own laptop, and commit the traces back to the repo as a PR. A full-load annotator has 70 task-conditions = 140 attempts; a duplicate annotator has 8–9 task-conditions = 16–18 attempts.

The plan covers a curated 140-base-task panel out of the **519-task full benchmark** — 7 sandbox websites × 5 difficulty levels × 4 base tasks per cell. Across the four full-load annotators that gives **560 primary attempts**, plus a **lightweight duplicate-human stability audit** of 35 task-conditions × 2 attempts = **70 duplicate attempts**, for **630 total expected attempts**.

The launcher handles everything: start backend + env dev servers, open a dashboard filtered to your assignments, step you through cold → warm, and optionally a 30-second feedback form.

## TL;DR

```bash
git clone git@github.com:<org>/BREAKINGWEB.git
cd BREAKINGWEB
./scripts/breakingweb.sh build          # one-time: install deps + build SPAs
./scripts/human-record.sh <YourName>      # e.g. P1, P2, P3, P4, D1, D2, D3, D4
# Browser opens automatically at http://localhost:8080/static/human.html?annotator=<YourName>
# When done:
git add breakingweb/human/traces/<YourName>/
git commit -m "human traces: <YourName>"
git push && open a PR
```

---

## 1. Prerequisites (one-time)

You need:

- **Python 3.11+** with the repo's venv (`uv sync` or `python -m venv .venv && pip install -e .` — same setup as the agent side).
- **Node 24+** and **pnpm** (the repo's env SPAs are a pnpm workspace).
- A **Chromium-based browser** (Chrome / Edge / Brave). We don't test Safari / Firefox.
- ~3 GB free disk for node_modules + build output.

One-time build:

```bash
./scripts/breakingweb.sh build
```

This installs all env dependencies and builds static bundles. You only need to re-run `build` if someone changes an env SPA; the recording launcher will use them as-is.

---

## 2. Start a recording session

```bash
./scripts/human-record.sh <YourName>
# e.g. ./scripts/human-record.sh P4
```

By default this starts all 7 env dev servers so you can jump between websites without restarting. If you want to record only one env at a time:

```bash
./scripts/human-record.sh P4 --env booking
```

The script prints your assignment portfolio up front:

```
  Annotator:     P4
  Assignments:   70 task-conditions (primary + duplicate)
  Attempts:      140 (cold + warm each)
  Env portfolio: {'amazon': 20, 'gmail': 10, 'lms': 20, 'patient_portal': 20}
```

…then opens your browser to:

```
http://localhost:8080/static/human.html?annotator=P4
```

Leave the terminal running; Ctrl-C when you're done for the day.

---

## 3. Record one assignment (cold + warm + form)

Each task card on the dashboard shows env, difficulty badge, condition (clean / intervention), and title — no cold/warm buttons. Clicking **Start** opens **two browser windows**:

- **Env tab** — a pristine copy of the env (Gmail / Amazon / etc) with no benchmark UI. This is where you interact with the website like a real user.
- **Control tab** — the task instruction, live recording stats (elapsed / events), and the **Evaluate** / **Abandon** buttons.

You read the instruction in the Control tab, act in the Env tab, and come back to the Control tab to finish. The Control tab drives the whole cold → warm → form flow for this one assignment; you don't return to the dashboard between cold and warm.

### Walkthrough

1. **Start.** Click Start on a dashboard card. Two windows open (allow popups for localhost). The dashboard stays where it is — you can minimize it.
2. **Read the instruction.** The control tab shows the full task description including resolved targets (e.g. "Reply to *Bob Martinez*'s email with subject *Meeting Tomorrow at 2pm*…"). A 10-second countdown runs while you read. Click **Start now** to skip the countdown, or just wait for auto-start.
3. **Do the cold attempt.** Once recording starts, switch to the env tab and perform the task naturally. The control tab shows a live REC indicator, elapsed time, and event count. Don't worry if you mess up or are slow — that's what cold is for.
4. **Evaluate.** When you're done, come back to the control tab and click **Evaluate**. The backend scores the session, stops recording, and saves the trace to:

   ```
   breakingweb/human/traces/<YourName>/<role>/<env>/<base_task_id>/<condition>/cold/
       metadata.json
       trace.json
   ```

5. **Start warm.** The control tab now shows pass/fail + reasoning + a **Start warm attempt →** button. Click it. The session resets (env tab reloads automatically at the same start page, seed 42 rebuilds fresh state), and recording re-starts after a short countdown. You do the task again — faster this time since you know what to do.
6. **Evaluate warm.** Same Evaluate flow as cold. After warm saves, the assignment is **already marked complete** on the dashboard. The control tab offers two buttons:
   - **Done — close windows** (most of the time, click this).
   - **Leave optional feedback…** if you want to flag a bug / ambiguity / alternate strategy. The form is fully optional — you can also submit it blank or just type one line. See GUIDELINES §6.
7. **Close.** Both windows can close. The dashboard card flips to ✓ Done within 10 seconds (it polls) — or click Refresh to see it immediately. Pick the next card.

### Pausing and resuming — cold + warm must be atomic

**You cannot split cold and warm across sessions.** If you close the control tab or env tab after saving cold but before warm evaluates, that assignment rolls back to "not started." Next time you click Start, you're doing cold again.

This is by design: warm is meant to measure how much faster you get after *just-seen* experience, so warm-after-forgetting doesn't count.

The dashboard itself is resumable indefinitely — come back tomorrow and your completed cards are preserved. Just don't leave an assignment half-done.

### What Abandon does to your trace files

When you click **Abandon** (or re-Start a previously-completed assignment), the backend:

1. Wipes the `cold_done` / `warm_done` flags in `progress.json` so the dashboard treats the assignment as not-started.
2. Stamps any existing `cold/metadata.json` + `warm/metadata.json` with `"abandoned": true` and `"abandoned_at": "<timestamp>"`. **Files are kept on disk** — abandoned attempts are still useful as data, and analysts filter them out by the flag.

So after an Abandon you'll see leftover folders under `breakingweb/human/traces/<YourName>/...` in `git status`. That's expected. Commit them along with the rest — don't manually delete.

If you redo the same assignment later and Evaluate cleanly, the new save overwrites the metadata file (without the `abandoned` key), so the marker is gone automatically.

### Recording etiquette

- **No DevTools inspection.** Don't open F12 to read task state or variant YAMLs.
- **Keep the env tab focused during the attempt.** Clicks elsewhere aren't recorded.
- **Don't resize the env window mid-attempt.** Viewport is captured once at save time; consistency matters across your cold+warm pair.
- **If something feels broken** (eval returns an unexpected fail, instruction references a missing element, intervention does nothing): click **Abandon**, mention it in the post-task form's "suspected bug" checkbox on a later attempt, or ping the project maintainer.

---

## 4. Submit your traces

Your traces live under `breakingweb/human/traces/<YourName>/`. That path is *not* gitignored (the rest of `trajectory/` / `trajectories/` is). When you're done for the week:

```bash
git checkout -b human-traces-<YourName>-w<N>
git add breakingweb/human/traces/<YourName>/
git commit -m "human: <YourName> week N traces (X assignments, Y attempts)"
git push origin HEAD
```

Open a PR against `main`. The project maintainer merges and aggregates. Don't touch anyone else's subdirectory.

Expected PR size:
- Full-load weekly target: ~10–15 assignments (20–30 attempts).
- Duplicate weekly target: ~4 assignments (8 attempts) — it's a smaller load.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "No assignments for annotator 'X'" | Name typo | Use exactly: P1, P2, P3, P4, D1, D2, D3, D4 (case-insensitive). |
| Popup blocked notice | Browser blocked popups | Allow popups for `localhost` in browser settings, then click Start again. |
| Control tab shows "Env tab unresponsive" | You closed the env tab | Click **Reopen env tab** in the warn banner. |
| Env tab shows "Not Found" | Env SPA isn't running | Check the launcher terminal for `[frontend:<env>]` lines. If missing, rerun `./scripts/breakingweb.sh build` then retry. |
| Evaluate returned error after 15s | Env tab isn't posting the trace back (possibly refreshed by hand) | Click Abandon, start over. |
| Browser didn't auto-open | Headless env / xdg-open missing | Copy the URL printed by the launcher manually. |
| Suspected task bug | Ambiguous instruction, evaluator bug, broken intervention | Abandon the attempt. On a future attempt of the same task (or a different clean/intervention pair on the same base task), tick "suspected bug" in the post-task form and add a note. Ping the maintainer with the `aid`. |
| `git status` shows leftover trace files after I abandoned | Expected — Abandon stamps `"abandoned": true` into metadata but keeps the files for analysis. | Commit them as-is. See [§3 "What Abandon does to your trace files"](#what-abandon-does-to-your-trace-files). |

---

## 6. Quality checks done by the system

You don't have to memorize the rules. The system already enforces:

- No annotator is assigned an env they designed (`designer_exclusions` in the YAML).
- Clean and intervention of the same base task go to different primary annotators.
- `cold` must save before `warm` can save. If you try to warm without cold, the backend returns 400.
- `form` is optional — the assignment is complete as soon as both cold and warm are saved.
- Starting a new attempt on an assignment **wipes any partial progress** for that assignment — this is what makes cold+warm atomic.
- Fixed seed 42 across everyone's recordings.
- `primary_primitive` / `expected_steps` / `variant_id` / intervention description are **hidden from the annotator UI** so your behavior isn't biased by the primitive label.
- The env tab renders the website exactly as it would for a real end user — no banner, no badges, no benchmark toolbar visible. Everything benchmark-related lives in the separate Control tab.

---

## 7. File layout (for curious folks)

```
breakingweb/human/
├── README.md                 # this file
├── assignments_v1.yaml       # source of truth: 280 primary + 35 duplicate rows
├── assignment_summary.md     # per-annotator totals, difficulty balance, etc.
└── traces/
    └── <YourName>/
        ├── progress.json     # per-assignment cold_done/warm_done/form_done flags
        └── <role>/<env>/<base_task_id>/<condition>/
            ├── post_task_form.json
            ├── cold/
            │   ├── metadata.json
            │   └── trace.json   # events[] + audit_log[] + evaluation
            └── warm/
                ├── metadata.json
                └── trace.json
```

The `trace.json` is the primary artifact for analysis: DOM events from `trajectory-recorder.js` (clicks / inputs / scrolls / navigations) plus the server-side audit_log plus the evaluator verdict. Metadata carries annotator / attempt / timing / variant / viewport info.

Questions → #breakingweb Slack, or ping the project maintainer.
