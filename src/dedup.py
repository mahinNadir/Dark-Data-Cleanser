"""Phase 1 cleaning: remove folder copies and exact duplicates inside each mailbox.

1. Drop catch-all folders that are almost purely copies of other folders.
2. Drop exact copies (md5 of cleaned subject + body) WITHIN each user only.
3. Save emails that appear in 2+ users' mailboxes as candidate duplicates for Phase 2.
   (They also stay in the main output; cross-user copies are not removed here.)
"""
import hashlib
import json
import os

import pandas as pd

IN_PATH = "data/interim/enron_emails.parquet"
OUT_PATH = "data/interim/emails_deduped.parquet"
CANDIDATES_PATH = "data/interim/cross_user_duplicate_candidates.parquet"
STATS_PATH = "data/interim/dedup_stats.json"

CATCH_ALL = {"all_documents", "discussion_threads", "sent_items"}
KEEP_SENT, DROP_SENT = "_sent_mail", "sent"  # keep one of the two per user, never both
SURVIVOR_ORDER = {"inbox": 0, KEEP_SENT: 1, DROP_SENT: 2}  # which copy survives dedupe


def md5_text(s: str) -> str:
    return hashlib.md5(s.strip().lower().encode("utf-8", "replace")).hexdigest()


df = pd.read_parquet(IN_PATH)
stats = {"rows_in": len(df)}

df["hash"] = (df["subject"].fillna("") + df["body"].fillna("")).map(md5_text)

# Top-level folder name, so "inbox/old" is judged as "inbox"
top = df["folder"].fillna("").str.lower().str.split(r"[\\/]", n=1, regex=True).str[0]

# For reference: how many within-user copies exist before any folder is dropped
stats["exact_dups_within_user_before_folder_drop"] = int(df.duplicated(["user", "hash"]).sum())

# ---- 1. drop catch-all folders (and the redundant sent folder) ----
is_catch_all = top.isin(CATCH_ALL)
users_with_keep_sent = df.loc[top == KEEP_SENT, "user"].unique()
is_redundant_sent = (top == DROP_SENT) & df["user"].isin(users_with_keep_sent)

stats["dropped_catch_all_folders"] = int(is_catch_all.sum())
stats["dropped_catch_all_by_folder"] = top[is_catch_all].value_counts().to_dict()
stats["dropped_redundant_sent_folder"] = int(is_redundant_sent.sum())

drop = is_catch_all | is_redundant_sent
df, top = df[~drop], top[~drop]
stats["rows_after_folder_drop"] = len(df)

# ---- 2. drop exact copies within each user ----
priority = top.map(SURVIVOR_ORDER).fillna(len(SURVIVOR_ORDER))
deduped = (
    df.assign(_prio=priority)
    .sort_values("_prio", kind="stable")  # inbox / sent copy wins over other folders
    .drop_duplicates(subset=["user", "hash"])
    .drop(columns="_prio")
    .sort_index()
    .reset_index(drop=True)
)
stats["within_user_exact_dups_removed"] = stats["rows_after_folder_drop"] - len(deduped)
stats["rows_out"] = len(deduped)

# ---- 3. cross-user copies -> candidate duplicates for Phase 2 ----
n_mailboxes = deduped.groupby("hash")["user"].transform("nunique")
candidates = deduped[n_mailboxes > 1].assign(n_mailboxes=n_mailboxes).sort_values(["hash", "user"])
stats["cross_user_duplicate_groups"] = int(candidates["hash"].nunique())
stats["cross_user_duplicate_rows"] = len(candidates)

# ---- save ----
for p in (OUT_PATH, CANDIDATES_PATH, STATS_PATH):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)  # "" when the path has no folder part
deduped.to_parquet(OUT_PATH)
candidates.reset_index(drop=True).to_parquet(CANDIDATES_PATH)
with open(STATS_PATH, "w") as f:
    json.dump(stats, f, indent=2)

print(json.dumps(stats, indent=2))