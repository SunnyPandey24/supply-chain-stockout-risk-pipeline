"""
Stockout Risk Classifier
=========================
Business problem: predict whether a SKU/warehouse will stock out at any
point in the next 14 days, using only information available today
(current stock, recent sales velocity/volatility, supplier lead time
and reliability). The output feeds a weekly "which SKUs need a PO this
week" action list.

Why this metric, not just accuracy:
A missed stockout (false negative) costs lost sales and a frustrated
customer. A false alarm (false positive) costs one unnecessary review
of a PO that turns out to be fine. The cost is asymmetric, so the model
is tuned for RECALL on the positive (stockout) class — we'd rather flag
some SKUs that turn out fine than miss a real stockout — while reporting
precision so the resulting workload is still usable by a human.
"""
import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    average_precision_score, confusion_matrix, classification_report
)

df = pd.read_csv("data/processed/model_features.csv", parse_dates=["date"])
df = pd.get_dummies(df, columns=["category"], prefix="cat")

feature_cols = [c for c in df.columns if c not in
                ["date", "sku", "warehouse_id", "stockout_within_14d"]]
X = df[feature_cols]
y = df["stockout_within_14d"]

# Time-based split (chronological) — avoids leaking future info into
# training, which a random split would do since rows from the same
# sku/warehouse series are correlated across time.
cutoff = df["date"].quantile(0.75)
train_mask = df["date"] <= cutoff
X_train, X_test = X[train_mask], X[~train_mask]
y_train, y_test = y[train_mask], y[~train_mask]

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

models = {
    "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
    "random_forest": RandomForestClassifier(
        n_estimators=300, max_depth=8, min_samples_leaf=5,
        class_weight="balanced", random_state=42),
}

results = {}
for name, model in models.items():
    if name == "logistic_regression":
        model.fit(X_train_s, y_train)
        proba = model.predict_proba(X_test_s)[:, 1]
    else:
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]

    # choose threshold that targets recall >= 0.75 on the positive class
    thresholds = np.linspace(0.05, 0.95, 19)
    best = max(
        thresholds,
        key=lambda t: (recall_score(y_test, proba >= t) >= 0.75, precision_score(y_test, proba >= t, zero_division=0))
    )
    preds = proba >= best

    results[name] = {
        "threshold": round(float(best), 2),
        "precision": round(precision_score(y_test, preds, zero_division=0), 3),
        "recall": round(recall_score(y_test, preds), 3),
        "f1": round(f1_score(y_test, preds), 3),
        "roc_auc": round(roc_auc_score(y_test, proba), 3),
        "pr_auc": round(average_precision_score(y_test, proba), 3),
        "confusion_matrix": confusion_matrix(y_test, preds).tolist(),
    }
    print(f"\n=== {name} ===")
    for k, v in results[name].items():
        print(f"{k}: {v}")

best_model_name = max(results, key=lambda n: results[n]["roc_auc"])
print(f"\nSelected model: {best_model_name}")

final_model = models[best_model_name]
final_threshold = results[best_model_name]["threshold"]

# ---- feature importance / coefficients ----
if best_model_name == "random_forest":
    importances = pd.Series(final_model.feature_importances_, index=feature_cols)
    importances = importances.sort_values(ascending=False)
    print("\nTop feature importances:")
    print(importances.head(8).round(3))
    importances.to_csv("data/processed/feature_importance.csv", header=["importance"])
else:
    coefs = pd.Series(final_model.coef_[0], index=feature_cols)
    coefs = coefs.reindex(coefs.abs().sort_values(ascending=False).index)
    print("\nTop standardized coefficients (logistic regression):")
    print(coefs.head(8).round(3))
    coefs.to_csv("data/processed/feature_importance.csv", header=["coefficient"])

joblib.dump({"model": final_model, "scaler": scaler if best_model_name == "logistic_regression" else None,
             "feature_cols": feature_cols, "threshold": final_threshold,
             "model_name": best_model_name}, "data/processed/stockout_model.joblib")

pd.Series(results).to_json("data/processed/model_metrics.json", indent=2)

# =====================================================================
# Apply the model to the LATEST snapshot -> the live risk score table
# =====================================================================
latest = pd.read_csv("data/processed/latest_snapshot_features.csv")
latest_enc = pd.get_dummies(latest, columns=["category"], prefix="cat")
for c in feature_cols:
    if c not in latest_enc.columns:
        latest_enc[c] = 0
X_live = latest_enc[feature_cols]

if best_model_name == "logistic_regression":
    risk_proba = final_model.predict_proba(scaler.transform(X_live))[:, 1]
else:
    risk_proba = final_model.predict_proba(X_live)[:, 1]

latest["stockout_risk_score"] = risk_proba.round(3)
latest["risk_tier"] = pd.cut(
    latest["stockout_risk_score"],
    bins=[-0.01, 0.3, 0.6, 1.0], labels=["Low", "Medium", "High"]
)
latest["recommended_action"] = np.select = np.where(
    latest["risk_tier"] == "High", "Place PO this week",
    np.where(latest["risk_tier"] == "Medium", "Monitor / review in 7 days", "No action needed")
)

latest.to_csv("data/processed/model_output.csv", index=False)
print("\nLive risk scoring complete:", len(latest), "sku-warehouse pairs")
print(latest.risk_tier.value_counts())
