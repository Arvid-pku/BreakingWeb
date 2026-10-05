# BreakingWeb

**Constructing Challenging Browser-Use Tasks by Controlled Environment Interventions**

[Paper](https://arxiv.org/abs/2609.35814) · [Website](https://www.breakingweb.app/) · [Live demo](https://tianchenguan-breakingweb-demo.hf.space) · [Data](https://huggingface.co/BreakingWeb)

BreakingWeb constructs challenging browser-use tasks by applying controlled, recoverable interventions to self-hosted web environments. Each clean/intervention pair preserves the user instruction, latent target, and backend success criterion. The paired performance difference measures the cost of the intervention.

The benchmark evaluates **519 task pairs** across **7 environments**—Gmail, Amazon, Reddit, Robinhood, Booking, an LMS, and a patient portal—with **29 intervention families**. Interventions act on seeded content, server state, network responses, or client-side interaction. Cognitive-primitive labels describe the recovery behaviors they primarily demand.

## Quick start

Requires Python 3.11+, Node.js 24+, and pnpm.

```bash
git clone https://github.com/Arvid-pku/BreakingWeb.git
cd BreakingWeb

uv sync --python 3.11 --extra browser-use
uv run playwright install chromium
pnpm -C breakingweb/environments install
./scripts/breakingweb.sh build
./scripts/breakingweb.sh dev
```

Open `http://localhost:8080/launch` to select a task and run its clean or intervention condition.

## Evaluate an agent

Configure your provider credentials in `breakingweb/.env` using [`.env.example`](breakingweb/.env.example). With the backend running, evaluate a task through the Browser-Use harness:

```bash
uv run python -m breakingweb.stock_browseruse_eval \
    --model gpt-5.4 \
    --provider openai \
    --tasks gmail_star_email \
    --max-steps 40 \
    --frontend-port 8080
```

The evaluator checks the final backend state against the task's success criteria. The run writes scores, trajectories, and screenshots to `breakingweb/results/stock_bu_run/`.

See the [harness guide](breakingweb/README.md) for model providers, intervention runs, and the screenshot-only BrowserGym harness.

## Code and data

| Component | Location |
|---|---|
| Task definitions | [`breakingweb/tasks/`](breakingweb/tasks/) |
| Intervention variants | [`breakingweb/injector/variants/`](breakingweb/injector/variants/) |
| Web environments | [`breakingweb/environments/`](breakingweb/environments/) |
| Backend and evaluator | [`breakingweb/backend/`](breakingweb/backend/), [`breakingweb/eval_core/`](breakingweb/eval_core/) |
| Human evaluation protocol | [`breakingweb/human/GUIDELINES.md`](breakingweb/human/GUIDELINES.md) |

The code includes 519 base tasks and 535 available intervention variants; the paper evaluates a 519-pair selection. Evaluation artifacts are available in [breakingweb-results-v2](https://huggingface.co/datasets/BreakingWeb/breakingweb-results-v2) and [breakingweb-results-v3](https://huggingface.co/datasets/BreakingWeb/breakingweb-results-v3).

## Citation

```bibtex
@misc{yin2026constructingchallengingbrowserusetasks,
      title={Constructing Challenging Browser-Use Tasks by Controlled Environment Interventions},
      author={Xunjian Yin and Tianchen Guan and Jinao Wang and Weili Cao and Daisy Xinlei Lin and Royce Cheng-Yue and Keagan Long and Kyle Wong and Bhuwan Dhingra and Xiangjun Wang and Shuyan Zhou},
      year={2026},
      eprint={2609.35814},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2609.35814},
}
```
