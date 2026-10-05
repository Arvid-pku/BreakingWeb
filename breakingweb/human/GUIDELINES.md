# BreakingWeb — Annotator Guidelines

This is the how-to-behave guide. For the how-to-install/run guide, see [`README.md`](./README.md).

**In one sentence:** each assignment is one base task under one condition (clean or intervention), recorded twice by you (cold → warm) at seed 42; the launcher drives the whole flow and you never need to touch the backend or look at task YAMLs.

---

## 0. Why we are collecting these traces

These recordings are used to measure the human side of BreakingWeb.

Each trace helps us compute:

| Output | Why it matters |
|---|---|
| Cold success / time / steps | Human first-pass baseline |
| Warm success / time / steps | Efficient human reference path |
| Cold → warm improvement | How much task familiarity matters |
| Human intervention tax | Whether the intervention is reasonable for humans |
| Agent / human efficiency ratio | Whether agents solve tasks as efficiently as humans |
| Duplicate trace stability | Whether one warm trace is stable enough as a reference |

The goal is not to solve tasks perfectly on the first try. A failed cold attempt is still useful data. Warm attempts and duplicate traces help us build reliable human references.

---

## 0.5. Who is doing what

The study has two annotator tiers. Check which one you are:

| Your role | Who | Load | Notes |
|---|---|---|---|
| **Primary (full-load)** | P1, P2, P3, P4 | 70 task-conditions each → 140 attempts (cold + warm) | You cover both clean + intervention across 3–4 environments. You are the primary human reference. |
| **Duplicate (limited-load, Amazon team)** | D1, D2, D3, D4 | 8–9 task-conditions each → 16–18 attempts | You re-record a subset of task-conditions that a primary annotator already did. This is a **lightweight duplicate-human stability audit** — 35 duplicated task-conditions in total (one per environment × difficulty cell), split across the four of you. Your traces are compared against the primary annotator's to estimate human-reference stability and catch task ambiguity. You don't need to match what the primary did — just record naturally. |

Both tiers use the same launcher and follow the same rules below. The dashboard automatically filters to your assigned set when you type your name.

---

## 1. What you are recording

A **task-condition** is one base task under one condition:

- **Clean:** the normal task environment.
- **Intervention:** the same user goal, but the website may contain a realistic complication — a transient failure, a lookalike distractor, stale state, a delayed update, a misleading banner, etc.

You do **not** need to know which mechanism (if any) is hidden in an intervention. Just solve the task as a careful user would. That's the whole point of the study.

For every assigned task-condition, you record two attempts back-to-back in the same session:

| Attempt | Meaning | How to behave |
|---|---|---|
| **Cold** | Your first try on this exact task-condition at seed 42. | Read the instruction, then solve naturally. Don't preview anything, don't ask for hints, don't inspect backend state. |
| **Warm** | A repeat immediately after cold, with the env reset to the same initial state. | Use what you learned in cold. Aim for correct and efficient, not sloppy. |

A **failed cold attempt is still useful data**. Save it; don't hide it. Warm is where you demonstrate the correct path.

---

## 2. Before you start

1. Install prerequisites once (see README §1).
2. Launch with:
   ```
   ./scripts/human-record.sh <YourName> [--env <id>|all]
   ```
   Your dashboard opens at `http://localhost:8080/static/human.html?annotator=<YourName>`.
3. Confirm the dashboard shows only your assigned tasks.
4. Use one monitor, standard window size, default zoom (100%), default browser. Allow popups for `localhost`.
5. Close unrelated browser tabs. Disable autofill, password managers, translation popups, ad blockers on the localhost tabs if they interfere.
6. Do **not** open DevTools, task YAML files, source code, evaluator checks, or backend API docs.
7. Do **not** ask another annotator or the task designer for task solutions before recording.

If the env tab ever shows primitive labels, intervention names, expected steps, seed digits, or evaluator internals — stop and report UI leakage to the project maintainer. You should only see the website and the task instruction.

---

## 3. Recording workflow

Each assignment opens **two windows**:

- **Env tab** — the website itself (Gmail / Amazon / etc). Pristine; no benchmark UI.
- **Control tab** — shows the task instruction, live recording indicator (elapsed time + event count), and the Evaluate / Abandon buttons.

You read the instruction in the control tab and act in the env tab. You **never return to the dashboard between cold and warm** — everything happens in the two windows.

### Step-by-step

1. **Click Start** on a dashboard card. Two windows open. The dashboard stays behind (minimize it).
2. **Read the instruction in the control tab.** A 10-second countdown auto-starts the recorder. Click **Start now** if you're ready earlier.
3. **Cold attempt.** Switch to the env tab and perform the task. Your DOM events (clicks, typing, navigation, scrolls) are captured automatically. Don't worry about being slow — cold is the natural baseline.
4. **Evaluate cold.** Back in the control tab, click **Evaluate**. The backend scores your session and saves the trace to:
   ```
   breakingweb/human/traces/<YourName>/<role>/<env>/<base_task_id>/<condition>/cold/
       metadata.json
       trace.json
   ```
5. **Warm attempt.** Click **Start warm attempt →**. The env rebuilds from the same seed; the env tab reloads automatically. Recording re-starts after a short countdown. Redo the task, faster and more correctly this time.
6. **Evaluate warm.** Click Evaluate again. Warm saves to `.../warm/`. The dashboard card flips to ✓ Done within 10 seconds. **The assignment is complete at this point.**
7. **Close, or leave optional feedback.** Click **Done — close windows**, or click **Leave optional feedback…** if you want to flag a bug, ambiguity, or alternate strategy. The feedback form is fully optional.

That's one assignment. Pick the next card.

### Cold + warm must be atomic

If you close the control tab or env tab *after cold saves but before warm evaluates*, the assignment rolls back to not-started. Next time you click Start, you do cold again. This is by design — warm measures same-session improvement, so warm-after-a-cold-from-yesterday doesn't count.

The dashboard itself is indefinitely resumable — shut down today, come back tomorrow, your completed cards are preserved. Just don't leave a single assignment half-done.

---

## 4. What you may and may not do

### Allowed

- Use normal website controls: click, type, select, scroll, wait, open menus, use in-site search/filter.
- Retry an action if the website appears not to respond (interventions sometimes include one-shot failures — the second click is the intended fix).
- Verify persistent state by re-opening a page when the task involves settings, reservations, messages, orders, payment methods, etc.
- Take a break between assignments. The dashboard is stateless across sessions.
- Write honest notes in the optional form when something was confusing or broken.

### Not allowed

- **No DevTools.** No F12, no `View Source`, no Network panel, no hand-editing `localStorage`, no Console commands.
- **No backend inspection.** Don't call `/api/env/...` directly, don't open task YAMLs, don't read `/api/human/*` responses.
- **No out-of-band help.** Don't ask another annotator or an AI assistant how to solve a task before recording.
- **No URL bar / bookmark / history navigation** unless the task explicitly requires it.
- **No browser resize / zoom / display change** mid-attempt. Your viewport is captured once at save; consistency matters.
- **No editing saved traces** under `breakingweb/human/traces/`. If a run went bad, click Abandon and redo — don't delete files. Abandon stamps `"abandoned": true` into the metadata; we keep the file for analysis.
- **No sharing solutions** with other annotators before they finish the same assignment.
- **No changing seed, task, condition, or intervention variant** — the launcher controls all of that.

---

## 5. Handling unexpected behavior

Intervention tasks intentionally include realistic complications. Respond as a real user would: retry when reasonable, verify final state, ignore suspicious or irrelevant content.

**Rule of thumb:** Abandon is mostly for *technical* failures (broken page, wrong card, setup bug) — **not** for "I couldn't figure out the task". If the page still works, a failed cold attempt is valuable data. Save it, then go into warm and try again.

**What Abandon does to your files:** the assignment rolls back to "not started" *and* any on-disk `cold/metadata.json` / `warm/metadata.json` from the abandoned attempt is stamped with `"abandoned": true`. **Files are kept**, not deleted — abandoned recordings are still useful for analysis. Commit them as-is when you submit your weekly PR. (See README §3 "What Abandon does to your trace files".)

| Situation | What to do |
|---|---|
| Normal mistake during cold | Continue. If the final state fails, click **Evaluate** and save it anyway. Cold failures are useful. |
| Accidental mistake during warm | Finish if recoverable. Evaluate and save even if it fails. |
| Task feels hard / you're stuck / you don't know the answer | **Keep going.** Try for a reasonable time. Then click Evaluate and save whatever state you ended up in — even a failed attempt is valuable data. **Don't abandon just because it was difficult.** |
| Evaluator fails when you believe you succeeded | Save it. Flag "Suspected bug" in the feedback form **or** ping the Slack channel (§6). |
| Instruction is unclear | Solve your best interpretation. Flag "Ambiguous instruction" in feedback **or** Slack, especially if the ambiguity changed your answer. |
| Env tab blanked / frozen / infinite loader / login loop | *This* is what Abandon is for. Click **Abandon**, note it in feedback or Slack. |
| You clicked Start on the wrong card | Click **Abandon**, go back to dashboard, click Start on the right card. |
| Page is usable but the intervention seems impossible to recover from | Still try. Save the failed result. Flag in feedback / Slack. We want to see how the intervention plays out — not a clean-looking trace. |
| You see primitive labels / variant names / expected steps leaking in the UI | Stop immediately and report UI leakage on Slack. |

---

## 6. Post-task feedback — optional for clean runs, please-do for bugs / ambiguity

After the warm attempt saves, you see two buttons:
- **Done** — close both windows, move on. The assignment is already marked complete on the dashboard.
- **Leave feedback…** — open the form.

**When to skip:** the task worked normally, instruction was clear, evaluator behaved correctly — just click Done. You don't have to rate anything.

**When we really need your feedback:**

- **Suspected bug** (evaluator fails on what looked like a clean success, page behaves unexpectedly, intervention does nothing / does too much)
- **Ambiguous instruction** (you could have reasonably interpreted it multiple ways, especially if the ambiguity changed your answer)
- **Alternate strategy** that obviously-works but feels different from what the task probably intended
- **Intervention felt contrived / unfair / not human-reasonable**

For those cases, either fill the form **or** drop a short message on the `#breakingweb-human-traces` Slack channel. Slack is fine if you're on a roll and don't want to lose focus — just include the `aid` (shown on each card) and a one-liner. The project maintainer triages both.

Everything in the form itself is still optional — submit with only the checkbox ticked, or only a one-line comment, or ratings only. Whatever fits what you want to say.

| Field | When to use it |
|---|---|
| **Clarity (1–5)** | Was the instruction understandable? |
| **Realism (1–5)** | Does this feel like a realistic web task? |
| **Fun / demo value (1–5)** | Would this be a good demo for others? |
| **Intervention naturalness (1–5)** | Only for intervention tasks: did the complication feel plausible rather than contrived? |
| **Suspected bug** | The UI, evaluator, reset, or task setup seemed broken. |
| **Ambiguous instruction** | The instruction could reasonably be read in multiple ways. |
| **Alternate valid strategy** | You found another reasonable solution path. |
| **Comments** | Anything specific worth the maintainer's attention. |

Good comments are specific:

- "Save button flashed success but the setting reverted after refresh."
- "Instruction says 'earliest reservation' but two reservations share the same check-in date."
- "Warm shortcut: target lives under Settings → Payment Methods → Default, saves 4 clicks."
- "Task passed but I also changed an unrelated preference by mistake."

---

## 7. Submitting your traces

Your traces live under `breakingweb/human/traces/<YourName>/`. That path is **not gitignored** — it's meant to be committed. When you've done a meaningful batch:

```bash
git checkout -b human-traces-<YourName>-w<N>
git add breakingweb/human/traces/<YourName>/
git commit -m "human: <YourName> batch <N> (<count> assignments)"
git push origin HEAD
```

Open a PR against `main`. The project maintainer aggregates.

**Don't touch anyone else's subdirectory under `traces/`.**

---

## 8. Quick FAQ

**What if I already know the website?**
Fine. "Cold" means first attempt on this exact task-condition, not first time ever using the website.

**What if I saw a similar task earlier?**
Record normally. Don't slow down artificially. If familiarity materially changed your behavior, mention it in optional feedback.

**Should I optimize warm for the fewest possible clicks?**
Correctness first. Efficiency second. Don't skip verification steps to save one click.

**What if cold fails?**
Save the cold result, then reset to warm and try again. Failure is data.

**What if I discover a shortcut?**
Use it if it's normal website behavior (not a backend/URL trick). Tick "Alternate valid strategy" in optional feedback.

**What if I accidentally clicked Start on the wrong card?**
Click **Abandon** in the control tab. The dashboard forgets the in-flight attempt.

**What if the env tab closed accidentally?**
The control tab shows an "Env tab closed" warning with a **Reopen env tab** button. Click it, keep going.

**What if popups are blocked?**
The dashboard shows "Popup blocked — allow popups for localhost and retry." Allow popups in browser settings, click Start again.

**Can I pause mid-attempt and come back?**
No. Pause == redo. Assignment rolls back to not-started if you abandon mid-flow.

**How many should I do per day?**
Your call. Full-load annotators have 70 assignments total. At ~8 minutes/assignment (cold+warm) that's ~9 hours of recording. Splitting into 5–10 sessions of 1–2 hours is reasonable. Duplicate annotators only have 8–9 assignments — one afternoon is plenty.

**Who to contact for bugs?**
`#breakingweb-human-traces` on Slack, or the project maintainer directly. Include the `aid` (shown on each card) and a one-line description. See §6 for what counts as "please flag this".
