"""Phase 2 row filter

    pip install langdetect
    python src/filter_rows.py

Reads emails_cleaned.parquet (so near-duplicates are still there) and writes
emails_ready.parquet plus a small table of how many emails survive each filter.
"""
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, detect

DetectorFactory.seed = 0      # makes langdetect give the same answer every run

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data/interim/emails_cleaned.parquet"
OUT_PATH = ROOT / "data/processed/corpus_clean.parquet"
REPORT_PATH = ROOT / "data/interim/filter_report.csv"

SAMPLE = None                 # set to e.g. 2000 to try it on a few emails first (nothing is saved)

# Words/phrases that mark an email as machine-generated. Add your own.
AUTOMATED = (
    r"out of (?:the )?office|auto-?reply|automatic reply|automatically generated"
    r"|this is an automated|do not reply|no-?reply|undeliverable|mailer-daemon"
    r"|delivery (?:status )?notification|begin:vcalendar|has invited you|meeting request"
    r"|required attendees|calendar entry|system alert|^(?:accepted|declined|tentative|canceled)\s*:"
)

# ---- Step 0: load ----
df = pd.read_parquet(IN_PATH)
if SAMPLE:
    df = df.sample(SAMPLE, random_state=7)
col = "clean_body" if "clean_body" in df.columns else "body"   # the cleaned text
print(f"Loaded {len(df):,} emails, using the '{col}' column")
counts = [("Start", len(df))]

# ---- Step 1: too short (under 50 words) ----
df["n_words"] = df[col].fillna("").str.split().str.len()
df = df[df["n_words"] >= 50]
counts.append(("Under 50 words removed", len(df)))

# ---- Step 2: too long (over 5,000 words) ----
df = df[df["n_words"] <= 5000]
counts.append(("Over 5,000 words removed", len(df)))

# ---- Step 3: automated (calendar invites, out of office, system alerts) ----
# Look at the subject plus the first 300 characters, where those phrases show up.
head = (df["subject"].fillna("") + "\n" + df[col].str.slice(0, 300)).str.lower()
df = df[~head.str.contains(AUTOMATED, regex=True)]
counts.append(("Automated removed", len(df)))


# ---- Step 4: not English (slow, so it runs on what is left) ----
def is_english(text):
    try:
        return detect(text[:1000].replace("<URL>", " ").replace("<EMAIL>", " ")) == "en"
    except Exception:         # empty text, or no letters to go on
        return False


print(f"Detecting language on {len(df):,} emails.")
df = df[df[col].map(is_english)]
counts.append(("Not English removed", len(df)))

# ---- Step 5: report + save ----
report = pd.DataFrame(counts, columns=["step", "remaining"])
report["dropped"] = (-report["remaining"].diff()).fillna(0).astype(int)
report["% of start"] = (report["remaining"] / counts[0][1] * 100).round(1)
print("\n" + report[["step", "dropped", "remaining", "% of start"]].to_string(index=False))

if SAMPLE:
    print("\n(SAMPLE is set, so nothing was saved.)")
else:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns="n_words").reset_index(drop=True).to_parquet(OUT_PATH, index=False, compression="zstd")
    report.to_csv(REPORT_PATH, index=False)
    print(f"\nSaved {len(df):,} emails to {OUT_PATH}\nSaved the table to {REPORT_PATH}")