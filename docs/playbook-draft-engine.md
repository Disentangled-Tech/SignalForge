# Playbook-Driven Draft Engine (ORE)

This document describes how pack playbooks drive ORE (Outreach Recommendation Engine) draft generation: YAML shape, loader, critic extension, and how explainability and sensitivity flow into drafts. It aligns with the Architecture Contract: **Core = Facts**, **Packs = Interpretation** (see [pack_v2_contract.md](pack_v2_contract.md) and [CORE_VS_PACK_RESPONSIBILITIES.md](CORE_VS_PACK_RESPONSIBILITIES.md)). Outreach tone, templates, and constraints are pack-owned; the pipeline uses core signals and pack interpretation only.

---

## 1. Playbook YAML shape

ORE playbooks live under `packs/<pack_id>/playbooks/`. The default playbook name used by the pipeline is `ore_outreach` (see `app/services/ore/playbook_loader.DEFAULT_PLAYBOOK_NAME`).

### Required keys (for ORE draft generation)

| Key | Type | Description |
|-----|------|-------------|
| `pattern_frames` | `dict[str, str]` | Dimension key (e.g. `momentum`, `complexity`, `pressure`, `leadership_gap`) to generic, non-invasive framing text. Never cite specific events. |
| `value_assets` | `list` | Offer strings (e.g. "2-page Tech Inflection Checklist"). |
| `ctas` | `list` | Call-to-action strings (consent-based; e.g. "Want me to send that checklist?"). |

### Optional keys (M3–M5)

| Key | Type | Description |
|-----|------|-------------|
| `opening_templates` | `list[str]` | Optional email opening templates. |
| `value_statements` | `list` | Optional; can align with or extend `value_assets`. |
| `forbidden_phrases` | `list[str]` | Phrases the critic must flag in drafts (case-insensitive). Applied in addition to core critic rules (surveillance, urgency, CTA count, opt-out). |
| `tone` | `str` or `dict` | Tone instruction for the draft prompt. If a dict, keys can match `recommendation_type` (e.g. "Soft Value Share", "Low-Pressure Intro"); `default` is used when no match. |
| `sensitivity_levels` | `list[str]` | Optional allowlist: only entities whose `sensitivity_level` is in this list get a draft. Values: `"low"`, `"medium"`, `"high"` (case-insensitive). Missing or not a list = no restriction. Empty list = no draft (capped at Soft Value Share). |
| `channel` | `str` | Optional single outreach channel (e.g. `"LinkedIn DM"`, `"Email"`). **Currently implemented:** the loader normalizes it (strip; empty/whitespace → `None`). Pipeline persists it and defaults to `"LinkedIn DM"` when `None` (Issue #121 M4). |
| `enable_ore_polish` | `bool` or `str` | Optional; when `true` (or string `"true"`/`"yes"`, case-insensitive), ORE runs an LLM polish step before the critic and falls back to the original draft if the polished draft fails the critic. **Default: false** for backward compatibility (Issue #119). |
| `channels` | `list[str]` | **Reserved (Issue #117):** optional list of outreach channels for the Strategy Selector. The loader does not currently normalize or default this key; when implemented, missing or empty will default to `["LinkedIn DM"]`. |
| `soft_ctas` | `list` | **Reserved (Issue #117):** optional softer CTAs when stability cap applies. The loader does not currently normalize or default this key; when implemented, missing will default to `[]`. |

Existing playbooks (e.g. `fractional_cto_v1`) may define only the required keys; the loader supplies defaults for missing optional keys. The loader currently implements optional `channel` (string) only; `channels` and `soft_ctas` are reserved for the strategy selector. Schema validation allows these optional keys when present (see `app/packs/schemas._validate_playbooks` and `app/services/ore/playbook_schema.OREPlaybook`).

**Example** (excerpt from `packs/fractional_cto_v1/playbooks/ore_outreach.yaml`):

```yaml
pattern_frames:
  momentum: "When a team's pace picks up, tech decisions that worked earlier can start costing more."
  complexity: "When products add integrations/AI/enterprise asks, systems often need a stabilization pass."
  # ...
value_assets: ["2-page Tech Inflection Checklist", ...]
ctas: ["Want me to send that checklist?", ...]
forbidden_phrases: []   # optional
tone:                  # optional (M5)
  "Soft Value Share": "Use only gentle framing; no direct ask."
  "Low-Pressure Intro": "Brief intro and pattern only; one small next step."
  default: "Match the maximum outreach tier above."
```

---

## 2. Playbook loader

**Module:** `app/services/ore/playbook_loader.py`

- **Entry point:** `get_ore_playbook(pack, playbook_name="ore_outreach")`  
  Returns a normalized playbook dict. When `pack` is `None` or the playbook is missing, the loader uses module constants for `pattern_frames`, `value_assets`, and `ctas`, and defaults optional keys to empty list or `None`.
- **Normalization:** `_normalize_playbook(raw, playbook_name)` ensures:
  - `forbidden_phrases` is a list of non-empty strings (strip, filter non-strings).
  - `opening_templates`, `value_statements` are lists (default `[]`).
  - `tone` is preserved if `str` or `dict`; otherwise `None`.
  - `sensitivity_levels` is preserved if a list; otherwise `None`.
  - `channel` (string): when present and non-empty after strip, preserved; otherwise `None`. The pipeline defaults to `"LinkedIn DM"` when the normalized playbook has `channel` `None` (Issue #121 M4).
  - `enable_ore_polish`: normalized from YAML (`True`, or string `"true"`/`"yes"` → `True`; else `False`). Default `False` when missing (Issue #119).
  - `channels` and `soft_ctas` are not yet normalized by the loader; they are reserved for the strategy selector (Issue #117).

Consumers (draft generator, ORE pipeline, critic) use this single source of truth so that switching pack changes playbook content and behavior without code changes.

---

## 3. Critic extension (forbidden phrases)

**Module:** `app/services/ore/critic.py`

The critic enforces:

- Core rules: no surveillance phrases, no urgency language, single CTA, opt-out language, short paragraphs (see `docs/critic_rules.md`).
- **Pack forbidden phrases:** When the ORE pipeline passes `forbidden_phrases` from the playbook into `check_critic(subject, message, forbidden_phrases=...)`, the critic treats any draft containing one of those phrases (case-insensitive) as a violation. When `forbidden_phrases` is `None` or empty, behavior is unchanged (core rules only).

Pipeline usage: `check_critic(subject, message, forbidden_phrases=playbook.get("forbidden_phrases") or [])`.

---

## 4. Explainability and top signals (M4)

- **Source:** `ReadinessSnapshot.explain` (e.g. `top_events`). Only signal_id/category labels and safe framing text are used; **no raw observation text** is passed to the LLM (PRD invariant).
- **Pipeline:** `_build_explainability_context(snapshot, pack)` in `app/services/ore/ore_pipeline.py` builds:
  - An explainability snippet (e.g. "Top contributing categories: see TOP_SIGNALS below. Use for framing only; do not reference specific events.").
  - A list of top signal labels (from `event_type_to_label`, limited to a small number).
- **Draft generator:** `generate_ore_draft(..., explainability_snippet=..., top_signal_labels=...)` injects these into the prompt as `{{EXPLAINABILITY_SNIPPET}}` and `{{TOP_SIGNALS}}`. The prompt instructs the LLM to use them for framing only and never as "I saw you…" or specific events.

---

## 5. Sensitivity and tone gating (M5)

- **Tone constraint:** Derived from ESL context (e.g. when stability cap applies, max recommendation = "Soft Value Share"). The pipeline passes `tone_constraint` (e.g. "Soft Value Share") and playbook-derived `tone_definition` (from `playbook["tone"]` by `recommendation_type` or `default`) into the draft generator.
- **Draft generator:** `_build_tone_instruction(tone_constraint, tone_definition)` produces the string used as `{{TONE_INSTRUCTION}}` in the prompt. **sensitivity_level** is never sent to the LLM; only the derived tone constraint and playbook tone text are used.
- **Prompt:** The base template `app/prompts/ore_outreach_v1.md` (and any pack override) must include `{{TONE_INSTRUCTION}}`. When no tone constraint is set, the pipeline passes an empty string.

Tone gating is prompt-only: it does not change policy gate, critic, or ESL logic.

---

## 6. Data flow (summary)

1. **Resolve pack** → `resolve_pack(db, pack_id)` (analysis config: manifest, scoring, ESL, playbooks, prompt_bundles).
2. **Load playbook** → `get_ore_playbook(pack, "ore_outreach")` → normalized dict with required + optional keys.
3. **Policy gate** → Cooldown, stability cap, ESL suppress; optionally playbook `sensitivity_levels` (no draft if entity sensitivity not in list).
4. **Draft** → `generate_ore_draft(..., explainability_snippet, top_signal_labels, tone_constraint, tone_definition)` using pack prompt and playbook pattern_frames/value_assets/ctas.
5. **Critic** → `check_critic(subject, message, forbidden_phrases=playbook["forbidden_phrases"])`; on failure, pipeline may substitute a compliant fallback.
6. **Persist** → `OutreachRecommendation` with `pack_id`, `playbook_id="ore_outreach"` (or the playbook name used).

---

## 7. References

- [Outreach-Recommendation-Engine-ORE-design-spec.md](Outreach-Recommendation-Engine-ORE-design-spec.md) — ORE design, policy gate, message rules, template library.
- [pack_v2_contract.md](pack_v2_contract.md) — Pack v2 contract; Core = Facts, Packs = Interpretation.
- [CORE_VS_PACK_RESPONSIBILITIES.md](CORE_VS_PACK_RESPONSIBILITIES.md) — Outreach owned by pack (playbooks, offer type, outreach logic).
- [GLOSSARY.md](GLOSSARY.md) — Sensitivity & Context, ORE, ESL.
- Implementation plan: Issue #176 (playbook loader, draft engine, persist playbook_id).
