import pandas as pd

corpus = pd.read_parquet("corpus_clean.parquet")
teams = pd.read_csv("custodian_counts.csv")

print(f"Corpus rows: {len(corpus):,}")
print(f"Custodians in teams file: {len(teams)}")
print()

# keep only high-confidence mailboxes for ground-truth labeling
teams_confident = teams[teams["source"] == "manual"]
print(f"High-confidence ('manual') custodians: {len(teams_confident)}")

df = corpus.merge(
    teams_confident[["custodian", "team"]],
    left_on="user", right_on="custodian", how="inner"
)
print(f"Rows after merging corpus with confident teams: {len(df):,}")
print()

print("Emails available per team (full pool, before sampling):")
print(df["team"].value_counts())
print()

TARGET_PER_TEAM = 250
labeled_pool = pd.concat(
    [g.sample(min(len(g), TARGET_PER_TEAM), random_state=42) for _, g in df.groupby("team")]
)

print(f"Target per team: {TARGET_PER_TEAM}")
print("Actual sampled per team:")
print(labeled_pool["team"].value_counts())
print()

labeled_pool = labeled_pool.drop(columns=["custodian"])
labeled_pool.to_parquet("labeling_pool.parquet")
print(f"Saved labeling_pool.parquet — {len(labeled_pool):,} rows, {labeled_pool.shape[1]} columns")

remaining = df.drop(labeled_pool.index, errors="ignore")
unlabeled_pool = remaining.sample(min(5000, len(remaining)), random_state=42)
unlabeled_pool = unlabeled_pool.drop(columns=["custodian"])
unlabeled_pool.to_parquet("unlabeled_pool.parquet")
print(f"Saved unlabeled_pool.parquet — {len(unlabeled_pool):,} rows")
