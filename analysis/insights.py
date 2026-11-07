"""Reproduce every number used in the deck from smb_leads.csv.

python3 analysis/insights.py
"""
from pathlib import Path

import pandas as pd

L = pd.read_csv(Path(__file__).resolve().parents[1] / "backend" / "data" / "smb_leads.csv")
L["act"] = L.outcome == "Activated"
A = L[L.act]
acts = len(A)
drops = L.drop_reason.value_counts()

print(f"Leads {len(L)}, activated {acts} ({acts / len(L):.1%})")
print(f"Avg days lead->activation {A.days_lead_to_activation.mean():.1f}; status chases {A.customer_follow_up_calls.mean():.1f}")
print(f"CAC per activation Rs {L.acquisition_cost_inr.sum() / acts:,.0f}; median bundle Rs {A.monthly_bundle_value_inr.median():,.0f}")

print("\nFriction drops a digital journey can remove:")
friction = {
    "visit": ["Owner had no time for a visit", "Visit not scheduled by sales"],
    "quote": ["Quote too complex to understand", "Quote took too long to arrive"],
    "paperwork": ["Found paperwork too long", "Missing GST or Udyam document", "Authorised signatory not available",
                  "Document details did not match"],
    "install": ["Installation delayed beyond 21 days", "Customer cancelled before install"],
}
for k, reasons in friction.items():
    print(f"  {k:<10} {sum(drops[r] for r in reasons)}")

print("\nSegment economics:")
for seg, g in L.groupby("segment"):
    a = g[g.act]
    cac = g.acquisition_cost_inr.sum() / len(a)
    mrr = a.monthly_bundle_value_inr.mean()
    print(f"  {seg:<28} share {len(g) / len(L):.0%}  activation {len(a) / len(g):.1%}  CAC/act Rs {cac:,.0f}  "
          f"MRR Rs {mrr:,.0f}  payback {cac / mrr:.1f} mo  churn {(a.churned_within_6_months == 'Y').mean():.1%}")

print("\nLead source:")
for src, g in L.groupby("lead_source"):
    print(f"  {src:<18} activation {g.act.mean():.1%}  CAC/act Rs {g.acquisition_cost_inr.sum() / max(1, g.act.sum()):,.0f}")

print("\nChurn by number of status chases:",
      A.groupby(A.customer_follow_up_calls.clip(upper=5)).churned_within_6_months.apply(lambda s: round((s == 'Y').mean(), 3)).to_dict())
print("Activation by GSTIN:", L.groupby("has_gstin").act.mean().round(3).to_dict())
print("Activation by current provider:", L.groupby("current_provider").act.mean().round(3).to_dict())
print("Activation by language:", L.groupby("preferred_language").act.mean().round(3).sort_values().to_dict())

# Impact model: recover part of each friction drop, then apply today's downstream conversion.
down = {"visit": acts / 1974, "quote": acts / 861, "paperwork": acts / 588, "install": 1.0}
recover = {"visit": 0.40, "quote": 0.60, "paperwork": 0.50, "install": 0.30}
extra = sum(sum(drops[r] for r in friction[k]) * recover[k] * down[k] for k in friction)
print(f"\nImpact: +{extra:.0f} activations per 5,000 leads -> {(acts + extra) / len(L):.1%}; "
      f"CAC at same spend Rs {L.acquisition_cost_inr.sum() / (acts + extra):,.0f}; "
      f"extra ARR Rs {extra * 4 * A.monthly_bundle_value_inr.median() * 12 / 1e7:.1f} crore")
