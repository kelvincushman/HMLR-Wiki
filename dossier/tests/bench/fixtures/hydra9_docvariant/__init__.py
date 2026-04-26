"""Hydra9 Hard Mode — document-ingest variant.

HMLR's Hydra9 Hard Mode sends 21 isolated dialogue turns over 30 simulated
days, each in a fresh session with no prior context at inference time. The
final query must reconstruct a causal chain from long-term memory only.

This variant does the same thing with **documents**: 21 dated markdown
files dropped into ``raw/``, one per day. The final query must produce the
NON-COMPLIANT verdict by joining:

  1. An 8-hop entity-alias chain (Legacy-Phi → Phoenix → Aether → K-12 →
     Styx → River-9 → Charon → Tartarus-v3).
  2. An 8-step policy supersession cascade (v3 forbid → v3 revoked →
     v4 EU-only → v5 draft-ignored → v6 400k/day → v7 rogue global-ban →
     v8 revert-to-v6).
  3. A quantitative compliance check: Project Cerberus expects
     4.7-4.85M records/day, but current policy v6 caps at 400k/day.

The scenario mirrors HMLR's published Hydra9 example directly so results
are comparable. Distractor docs (Project Aegis, Apollo scheme) are
included to punish naive retrieval.
"""

from __future__ import annotations

# One dict per day. ``filename`` is dated for chronological ingest order.
# ``text`` is the doc body — intentionally conversational / internal-memo
# style, no repeated keywords that would make retrieval trivial.

HYDRA9_DOCS: list[dict[str, str]] = [
    {
        "filename": "2025-03-15_project_aegis_status.md",
        "text": (
            "# Project Aegis — status update\n\n"
            "Aegis continues on the Sentinel-IV telemetry stack. Telemetry "
            "volumes are nominal and within the allowance set by Policy v1. "
            "Nothing encryption-related to report.\n\n"
            "*(Distractor: unrelated project. Included to punish retrieval "
            "that keyword-matches on the word 'policy' or 'Project'.)*\n"
        ),
    },
    {
        "filename": "2025-03-18_legacy_phi_overview.md",
        "text": (
            "# Encryption scheme overview — internal memo\n\n"
            "The system engineering team still refers to the encryption "
            "scheme by its legacy codename **Legacy-Phi** (internal marker "
            "LΦ-88). Legacy-Phi has been through several renames since its "
            "original introduction — naming has not been our strong suit.\n"
        ),
    },
    {
        "filename": "2025-03-20_phoenix_history.md",
        "text": (
            "# Legacy naming note\n\n"
            "For anyone reading old design docs: before it was called "
            "Legacy-Phi, this scheme was called **Phoenix**. The Phoenix "
            "name appears in architecture diagrams from 2019 and 2020.\n"
        ),
    },
    {
        "filename": "2025-03-22_phoenix_renamed_aether.md",
        "text": (
            "# Rename notice — 2021\n\n"
            "In 2021, Phoenix was renamed to **Aether** as part of the "
            "product brand refresh. Internal docs from 2021 onward use "
            "Aether; pre-2021 docs still say Phoenix. They are the same "
            "encryption scheme.\n"
        ),
    },
    {
        "filename": "2025-03-24_aether_was_k12.md",
        "text": (
            "# Historical footnote\n\n"
            "A correction for archivists: Aether was itself previously "
            "called **K-12** in the earliest prototype branch. That name "
            "was dropped before public release but survives in some "
            "git-history commit messages. K-12 == Aether == (later) "
            "Phoenix renamed forward.\n"
        ),
    },
    {
        "filename": "2025-03-26_styx_legal_name.md",
        "text": (
            "# Legal department naming\n\n"
            "Legal prefers the formal name **Styx** when referring to the "
            "scheme in contracts. Styx is the official legal name for what "
            "marketing has been calling **River-9**. They are not separate "
            "schemes — same thing, two names, two audiences.\n"
        ),
    },
    {
        "filename": "2025-03-28_river9_marketing.md",
        "text": (
            "# Marketing materials note\n\n"
            "Marketing collateral uses **River-9** publicly. River-9 is the "
            "marketing name for **Charon** (the internal production name). "
            "Treat River-9 and Charon as aliases in customer-facing docs.\n"
        ),
    },
    {
        "filename": "2025-03-30_charon_to_tartarus.md",
        "text": (
            "# Production renaming — final\n\n"
            "Charon has been retired as a name. The final production name "
            "going forward is **Tartarus-v3**. All new deployment manifests "
            "should use Tartarus-v3 exclusively. Old Charon references in "
            "internal tools will be auto-translated by the deploy wrapper.\n"
        ),
    },
    {
        "filename": "2025-04-01_tartarus_v3_canonical.md",
        "text": (
            "# Canonical naming cut-over — effective March 1, 2025\n\n"
            "Per the March 1, 2025 cut-over, **Tartarus-v3** is the current "
            "and only supported name for this encryption scheme. All prior "
            "names (Legacy-Phi, Phoenix, Aether, K-12, Styx, River-9, "
            "Charon) are retired. Tartarus-v3 is the canonical reference.\n"
        ),
    },
    {
        "filename": "2025-04-03_policy_v3_forbids_charon.md",
        "text": (
            "# Policy v3 — effective immediately\n\n"
            "Under Policy v3, **Charon is forbidden entirely** from "
            "production workloads. No exceptions. Any team using Charon "
            "must migrate away. This policy supersedes the blank-slate v2.\n"
        ),
    },
    {
        "filename": "2025-04-06_policy_v3_footnote_revoked.md",
        "text": (
            "# Footnote to Policy v3 — three days later\n\n"
            "The restriction in Policy v3 has been **revoked** via footnote "
            "published three days after v3 itself. This footnote is "
            "load-bearing: any compliance analysis reading v3 without the "
            "footnote will draw the wrong conclusion. The revocation is "
            "official.\n"
        ),
    },
    {
        "filename": "2025-04-08_policy_v4_tartarus_eu.md",
        "text": (
            "# Policy v4 — regional usage\n\n"
            "Policy v4 approves **Tartarus-v3 without limit** for workloads "
            "operating in **EU regions only**. Non-EU usage remains governed "
            "by whatever v3 (post-revocation) left in place.\n"
        ),
    },
    {
        "filename": "2025-04-10_policy_v5_draft_ignored.md",
        "text": (
            "# Policy v5 — DRAFT (not in effect)\n\n"
            "Policy v5 was drafted but **never ratified**. Do not apply v5 "
            "constraints. Compliance reviewers: ignore v5 entirely. It "
            "exists in the archive but has no force.\n"
        ),
    },
    {
        "filename": "2025-04-13_policy_v6_400k_limit.md",
        "text": (
            "# Policy v6 — record-volume limit reinstated\n\n"
            "Policy v6 reinstates a **400,000 records/day** limit on "
            "Tartarus-v3 usage globally. This supersedes Policy v5 (which "
            "was ignored anyway) and formally closes the blanket EU "
            "allowance from v4.\n"
        ),
    },
    {
        "filename": "2025-04-15_apollo_offsite_notes.md",
        "text": (
            "# Notes from the Apollo scheme offsite — 2022 retrospective\n\n"
            "The Apollo scheme was discussed at the 2022 architecture "
            "offsite. Apollo was never related to Tartarus-v3 — it was an "
            "entirely separate symmetric-key effort that was archived. "
            "Included here for historical record only.\n\n"
            "*(Distractor: mentions 'scheme' and '2022' but unrelated.)*\n"
        ),
    },
    {
        "filename": "2025-04-18_policy_v7_global_ban.md",
        "text": (
            "# Policy v7 — global ban for >1 GiB/day\n\n"
            "Policy v7 institutes a **global ban on Tartarus-v3** for any "
            "workload exceeding 1 GiB/day. This supersedes all prior "
            "policies (v1 through v6) and replaces the 400,000 records/day "
            "cap with a volume-based cutoff.\n"
        ),
    },
    {
        "filename": "2025-04-21_policy_v7_rogue_memo.md",
        "text": (
            "# Internal memo — Policy v7 authorship\n\n"
            "Investigation complete: Policy v7 was **issued by a rogue "
            "employee** who lacked authorisation. The employee's access "
            "has been revoked. v7 was never signed by any authorised "
            "policy officer. It cannot stand.\n"
        ),
    },
    {
        "filename": "2025-04-23_policy_v8_reverts_to_v6.md",
        "text": (
            "# Policy v8 — revert to v6\n\n"
            "Policy v8 **reverts** the state set by the unauthorised "
            "Policy v7. Under v8, the governing policy on Tartarus-v3 "
            "usage is once again Policy v6: **400,000 records/day** limit "
            "globally. v8 is the current active policy.\n"
        ),
    },
    {
        "filename": "2025-04-25_project_cerberus_kickoff.md",
        "text": (
            "# Project Cerberus — kickoff\n\n"
            "Project Cerberus is spinning up. Cerberus handles archival "
            "encryption of customer telemetry at scale. The team is "
            "assembling now; the first deployment milestone is in six "
            "weeks.\n"
        ),
    },
    {
        "filename": "2025-04-28_cerberus_volume_estimate.md",
        "text": (
            "# Project Cerberus — capacity planning\n\n"
            "Volume estimates from the Cerberus capacity-planning sprint: "
            "Cerberus will encrypt between **4.7 and 4.85 million records "
            "per day** at steady state. Peak days may briefly exceed this. "
            "Planning assumes sustained 4.7M+ records/day baseline.\n"
        ),
    },
    {
        "filename": "2025-04-30_cerberus_will_use_tartarus.md",
        "text": (
            "# Project Cerberus — encryption-scheme selection\n\n"
            "Architecture review concluded. Cerberus will use "
            "**Tartarus-v3** as its encryption scheme. This decision is "
            "final pending a compliance review against the current policy "
            "state.\n"
        ),
    },
]


FINAL_QUERY = (
    "Project Cerberus is going to use Tartarus-v3 for encryption at its "
    "planned volume of 4.7 to 4.85 million records per day. Is this use "
    "compliant with the current policy? In your answer, state the "
    "compliance verdict (COMPLIANT or NON-COMPLIANT), list the full name "
    "chain for this encryption scheme, and list the policy versions in "
    "order with which one is currently active and why."
)


# Reference answer — mirrors HMLR's published example for this scenario.
FINAL_REFERENCE = (
    "NON-COMPLIANT. The encryption scheme has gone through the name chain "
    "Legacy-Phi (LΦ-88) → Phoenix → Aether → K-12 → Styx → River-9 → "
    "Charon → Tartarus-v3 (canonical after March 1, 2025). Policy history: "
    "v3 forbade Charon but was revoked by footnote three days later; v4 "
    "approved Tartarus-v3 without limit for EU regions only; v5 was a "
    "draft that was never ratified and must be ignored; v6 reinstated a "
    "400,000 records/day global limit; v7 instituted a global ban for "
    ">1 GiB/day workloads but was issued by an unauthorised rogue "
    "employee; v8 reverted to v6. Policy v6 is therefore the current "
    "active policy, capping Tartarus-v3 usage at 400,000 records/day. "
    "Cerberus's planned 4.7 to 4.85 million records/day vastly exceeds "
    "this limit, so the planned use is non-compliant."
)


# Binary pass/fail signals — mirror HMLR's verification style. A correct
# answer must contain all of these token sets (one from each row).
REQUIRED_TOKEN_SETS: list[list[str]] = [
    # compliance verdict
    ["NON-COMPLIANT", "non-compliant", "non compliant", "not compliant"],
    # name chain: at minimum the current and one prior name
    ["Tartarus-v3", "tartarus"],
    ["Charon", "charon"],
    # the active policy and its limit
    ["v6", "Policy v6", "400,000", "400000", "400k"],
    # recognition of the rogue-v7 / revert mechanism
    ["v7", "v8", "revert", "rogue", "unauthorised", "unauthorized"],
    # the quantitative mismatch
    ["4.7", "4.85", "exceed", "exceeds"],
]
