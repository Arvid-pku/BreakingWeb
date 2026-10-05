"""DEPRECATED: Legacy Playwright DOM mutation helpers.

Live client degradations are now delivered through the in-app React
BenchmarkToolbar component (`environments/shared/src/components/BenchmarkToolbar.tsx`),
which fetches `GET /api/env/gmail/degradation/{session_id}` and applies DOM
mutations in-browser for both human sessions and agent-mode sessions.

This module is retained for reference only. The Playwright page.evaluate()
approach below is no longer called by the benchmark harness.

Original design principles:
  1. FILTER not WALL — enough signal remains for agents with the primitive.
  2. DISTRIBUTED — persistent mode re-applies after every SPA navigation.
  3. DETERMINISTIC — no randomness in DOM mutations (structure is the signal).
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Persistent injection wrapper
# ---------------------------------------------------------------------------
# For persistent mode, we wrap the mutation JS in a self-re-applying script
# that uses MutationObserver to re-apply after DOM changes (SPA re-renders).

_PERSISTENT_WRAPPER = """
(function() {{
    const INJECTED_KEY = '__wab_injected_{action_id}';
    function apply() {{
        if (document[INJECTED_KEY]) return;
        document[INJECTED_KEY] = true;
        {inner_js}
        // Reset flag after a delay so it re-fires on next big DOM change
        setTimeout(() => {{ document[INJECTED_KEY] = false; }}, 2000);
    }}
    // Apply immediately
    apply();
    // Re-apply on DOM subtree modifications (SPA route changes)
    const observer = new MutationObserver((mutations) => {{
        // Only re-apply on significant changes (childList, not just attributes)
        const significant = mutations.some(m => m.type === 'childList' && m.addedNodes.length > 2);
        if (significant) {{ document[INJECTED_KEY] = false; apply(); }}
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
}})();
"""


async def apply_client_injection(page: Any, params: dict[str, Any]) -> None:
    """Apply a client-side injection to a Playwright page."""
    action = params.get("action", "")
    behavior = params.get("behavior", {})
    mode = behavior.get("mode", "oneshot")

    if action == "swap_labels":
        # Grounding: swap text of two elements.
        # Agent with grounding uses structural cues to disambiguate.
        js = """
            const a = document.querySelector('{selector_a}');
            const b = document.querySelector('{selector_b}');
            if (a && b) {{ const t = a.textContent; a.textContent = b.textContent; b.textContent = t; }}
        """.format(**{k: str(v).replace("'", "\\'") for k, v in params.items() if k not in ("action", "behavior")})

        if mode == "persistent":
            await page.add_init_script(_PERSISTENT_WRAPPER.format(action_id="swap_labels", inner_js=js))
            await page.evaluate(f"() => {{ {js} }}")
        else:
            await page.evaluate(
                """(p) => {
                const a = document.querySelector(p.selector_a);
                const b = document.querySelector(p.selector_b);
                if (a && b) { const t = a.textContent; a.textContent = b.textContent; b.textContent = t; }
            }""",
                params,
            )

    elif action == "add_decoy":
        # Grounding: clone element but strip functionality. Real element remains.
        if mode == "persistent":
            js = """
                const real = document.querySelector('{selector}');
                if (real && !real.previousElementSibling?.hasAttribute('data-decoy')) {{
                    const decoy = real.cloneNode(true);
                    decoy.removeAttribute('onclick');
                    decoy.removeAttribute('type');
                    decoy.setAttribute('data-decoy', 'true');
                    decoy.style.cursor = 'pointer';
                    real.parentNode.insertBefore(decoy, real);
                }}
            """.format(selector=str(params.get("selector", "")).replace("'", "\\'"))
            await page.add_init_script(_PERSISTENT_WRAPPER.format(action_id="add_decoy", inner_js=js))
            await page.evaluate(f"() => {{ {js} }}")
        else:
            await page.evaluate(
                """(p) => {
                const real = document.querySelector(p.selector);
                if (!real) return;
                const decoy = real.cloneNode(true);
                decoy.removeAttribute('onclick');
                decoy.removeAttribute('type');
                decoy.setAttribute('data-decoy', 'true');
                decoy.style.cursor = 'pointer';
                real.parentNode.insertBefore(decoy, real);
            }""",
                params,
            )

    elif action == "false_banner":
        # Grounding: misleading status message. Real state is still visible.
        await page.evaluate(
            """(p) => {
            const banner = document.createElement('div');
            banner.className = p.css_class || '';
            banner.textContent = p.message;
            banner.setAttribute('role', 'alert');
            banner.setAttribute('data-injected', 'true');
            const target = document.querySelector(p.insert_before) || document.body.firstChild;
            target.parentNode.insertBefore(banner, target);
        }""",
            params,
        )

    elif action == "hide_affordance":
        # Exploration: hide element behind non-obvious interaction.
        # Element IS there — just requires the right interaction to reveal.
        trigger = params.get("trigger", "contextmenu")
        selector = str(params.get("selector", "")).replace("'", "\\'")

        if mode == "persistent":
            js = f"""
                const el = document.querySelector('{selector}');
                if (el && el.style.display !== 'none') {{
                    el.style.display = 'none';
                    el.parentNode.addEventListener('{trigger}', () => {{ el.style.display = ''; }});
                }}
            """
            await page.add_init_script(_PERSISTENT_WRAPPER.format(action_id="hide_affordance", inner_js=js))
            await page.evaluate(f"() => {{ {js} }}")
        else:
            await page.evaluate(
                """(p) => {
                const el = document.querySelector(p.selector);
                if (!el) return;
                el.style.display = 'none';
                const trigger = p.trigger || 'contextmenu';
                el.parentNode.addEventListener(trigger, () => { el.style.display = ''; });
            }""",
                params,
            )

    elif action == "inject_script":
        # General: custom JS. Always persistent (addInitScript).
        await page.add_init_script(params.get("script", ""))

    elif action == "scramble_aria":
        # Grounding: shift ARIA labels. Other signals (text, structure) remain.
        selector = str(params.get("selector", "[aria-label]")).replace("'", "\\'")

        if mode == "persistent":
            js = f"""
                const els = document.querySelectorAll('{selector}');
                if (els.length > 1) {{
                    const labels = Array.from(els).map(e => e.getAttribute('aria-label'));
                    els.forEach((el, i) => {{
                        el.setAttribute('aria-label', labels[(i + 1) % labels.length]);
                    }});
                }}
            """
            await page.add_init_script(_PERSISTENT_WRAPPER.format(action_id="scramble_aria", inner_js=js))
            await page.evaluate(f"() => {{ {js} }}")
        else:
            await page.evaluate(
                """(p) => {
                const els = document.querySelectorAll(p.selector || '[aria-label]');
                const labels = Array.from(els).map(e => e.getAttribute('aria-label'));
                els.forEach((el, i) => {
                    el.setAttribute('aria-label', labels[(i + 1) % labels.length]);
                });
            }""",
                params,
            )
