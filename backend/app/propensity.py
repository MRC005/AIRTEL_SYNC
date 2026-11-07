"""Lead propensity score: which leads should a human call first?

Uses only what is known when the lead arrives (no funnel dates or outcomes, which would
leak the answer). Logistic regression is chosen over a black-box model so a sales manager
can see why a lead scored high.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA = Path(__file__).resolve().parent.parent / "data"
CATEGORICAL = ["lead_source", "segment", "preferred_language", "annual_turnover_band", "has_gstin",
               "has_udyam", "current_internet", "current_provider", "contact_role"]
NUMERIC = ["employee_count", "num_sites", "log_spend", "n_interests", "city_tier"]


def features(df: pd.DataFrame) -> pd.DataFrame:
    X = df[CATEGORICAL].astype(str).copy()
    X["employee_count"] = np.log1p(df["employee_count"].astype(float))
    X["num_sites"] = df["num_sites"].astype(float)
    X["log_spend"] = np.log1p(df["monthly_telecom_spend_inr"].astype(float))
    X["n_interests"] = df["products_of_interest"].fillna("").str.count(";") + 1
    X["city_tier"] = df["city_tier"].astype(float)
    return X


def make_model() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    return Pipeline([("pre", pre), ("lr", LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced"))])


@lru_cache
def trained() -> dict:
    leads = pd.read_csv(DATA / "smb_leads.csv")
    X, y = features(leads), (leads["outcome"] == "Activated").astype(int)
    cv = StratifiedKFold(5, shuffle=True, random_state=7)
    oof = cross_val_predict(make_model(), X, y, cv=cv, method="predict_proba")[:, 1]
    auc = roc_auc_score(y, oof)
    # Lift: share of all activations found by calling only the top 20% of scored leads.
    top = oof >= np.quantile(oof, 0.8)
    capture = y[top].sum() / y.sum()
    model = make_model().fit(X, y)
    leads["score"] = (model.predict_proba(X)[:, 1] * 100).round(0)
    return {"model": model, "auc": round(float(auc), 3), "top20_capture": round(float(capture), 3),
            "top20_rate": round(float(y[top].mean()), 3), "base_rate": round(float(y.mean()), 3), "leads": leads}


def top_drivers(n: int = 8) -> list[dict]:
    m = trained()["model"]
    names = m.named_steps["pre"].get_feature_names_out()
    coefs = m.named_steps["lr"].coef_[0]
    order = np.argsort(-np.abs(coefs))[:n]
    return [{"feature": names[i].split("__", 1)[1], "weight": round(float(coefs[i]), 2)} for i in order]


def call_list(limit: int = 25) -> list[dict]:
    """Leads the digital journey has not closed yet, highest score first.

    We show leads that dropped early for reasons a phone call can fix (no visit scheduled,
    owner had no time, could not be reached), not ones that said no.
    """
    leads = trained()["leads"]
    recoverable = ["Owner had no time for a visit", "Visit not scheduled by sales", "Unreachable after 3 attempts",
                   "Quote took too long to arrive", "Quote too complex to understand", "Found paperwork too long",
                   "Decided to wait"]
    open_ = leads[leads["drop_reason"].isin(recoverable)].sort_values("score", ascending=False).head(limit)
    cols = ["lead_id", "business_name", "business_type", "segment", "city", "preferred_language", "lead_source",
            "has_gstin", "drop_reason", "score"]
    return open_[cols].to_dict("records")
