#!/usr/bin/env python3
"""
Assign Enron (CMU maildir release) custodians to six teams and count emails per team.

Usage:
    python enron_teams.py /path/to/maildir
    python enron_teams.py /path/to/maildir --no-dedup --out results/

Outputs (in --out, default ./enron_team_output):
    custodian_counts.csv   one row per mailbox: custodian, team, source, raw/unique email counts
    team_summary.csv       one row per team: custodians, raw and unique email counts
    unassigned.csv         mailboxes not in TEAM_MAP, with a keyword-based team suggestion

Notes:
- Each file in the maildir is one email. The same message often appears in several
  folders (_sent_mail, sent, all_documents, discussion_threads), so by default emails
  are deduplicated per custodian by Message-ID. Use --no-dedup for raw file counts.
- TEAM_MAP is hand-built from custodians' known roles. Entries marked LOW_CONFIDENCE
  are best guesses; check them against the X-Folder / signature lines before using
  them as ground-truth labels.
"""

import argparse
import csv
import os
import re
from collections import Counter, defaultdict

TEAMS = [
    "Trading",
    "Legal",
    "Gov & Regulatory Affairs",
    "Pipelines (ETS)",
    "Operations, Risk & Research",
    "Executive & Corporate",
]

# custodian folder name -> team
TEAM_MAP = {
    # --- Trading (gas & power) ---
    "allen-p": "Trading", "arnold-j": "Trading", "arora-h": "Trading",
    "badeer-r": "Trading", "bass-e": "Trading", "baughman-d": "Trading",
    "benson-r": "Trading", "brawner-s": "Trading", "carson-m": "Trading",
    "crandell-s": "Trading", "cuilla-m": "Trading", "dorland-c": "Trading",
    "ermis-f": "Trading", "forney-j": "Trading", "gilbertsmith-d": "Trading",
    "griffith-j": "Trading", "grigsby-m": "Trading", "holst-k": "Trading",
    "keavey-p": "Trading", "kuykendall-t": "Trading", "lenhart-m": "Trading",
    "lucci-p": "Trading", "maggi-m": "Trading", "martin-t": "Trading",
    "may-l": "Trading", "mims-thurston-p": "Trading", "motley-m": "Trading",
    "neal-s": "Trading", "parks-j": "Trading", "platter-p": "Trading",
    "presto-k": "Trading", "quigley-d": "Trading", "reitmeyer-j": "Trading",
    "ring-a": "Trading", "ruscitti-k": "Trading", "saibi-e": "Trading",
    "scholtes-d": "Trading", "schwieger-j": "Trading", "shively-h": "Trading",
    "south-s": "Trading", "staab-t": "Trading", "stepenovitch-j": "Trading",
    "storey-g": "Trading", "sturm-f": "Trading", "swerzbin-m": "Trading",
    "tholt-j": "Trading", "thomas-p": "Trading", "townsend-j": "Trading",
    "tycholiz-b": "Trading", "ward-k": "Trading", "williams-w3": "Trading",
    "wolfe-j": "Trading", "zufferli-j": "Trading", "belden-t": "Trading",

    # --- Legal ---
    "bailey-s": "Legal", "cash-m": "Legal", "derrick-j": "Legal",
    "dickson-s": "Legal", "haedicke-m": "Legal", "heard-m": "Legal",
    "hodge-j": "Legal", "hyvl-d": "Legal", "jones-t": "Legal",
    "mann-k": "Legal", "nemec-g": "Legal", "panus-s": "Legal",
    "perlingiere-d": "Legal", "sager-e": "Legal", "sanders-r": "Legal",
    "shackleton-s": "Legal", "stclair-c": "Legal", "taylor-m": "Legal",

    # --- Government & Regulatory Affairs ---
    "dasovich-j": "Gov & Regulatory Affairs", "hain-m": "Gov & Regulatory Affairs",
    "kean-s": "Gov & Regulatory Affairs", "shapiro-r": "Gov & Regulatory Affairs",
    "steffes-j": "Gov & Regulatory Affairs", "mara-s": "Gov & Regulatory Affairs",

    # --- Pipelines / Enron Transportation Services ---
    "blair-l": "Pipelines (ETS)", "corman-s": "Pipelines (ETS)",
    "donoho-l": "Pipelines (ETS)", "fossum-d": "Pipelines (ETS)",
    "geaccone-t": "Pipelines (ETS)", "harris-s": "Pipelines (ETS)",
    "hayslett-r": "Pipelines (ETS)", "horton-s": "Pipelines (ETS)",
    "hyatt-k": "Pipelines (ETS)", "lokay-m": "Pipelines (ETS)",
    "lokey-t": "Pipelines (ETS)", "mccarty-d": "Pipelines (ETS)",
    "mcconnell-m": "Pipelines (ETS)", "schoolcraft-d": "Pipelines (ETS)",
    "scott-s": "Pipelines (ETS)", "watson-k": "Pipelines (ETS)",

    # --- Operations, Risk & Research ---
    "beck-s": "Operations, Risk & Research", "dean-c": "Operations, Risk & Research",
    "farmer-d": "Operations, Risk & Research", "gang-l": "Operations, Risk & Research",
    "germany-c": "Operations, Risk & Research", "giron-d": "Operations, Risk & Research",
    "guzman-m": "Operations, Risk & Research", "hernandez-j": "Operations, Risk & Research",
    "kaminski-v": "Operations, Risk & Research", "keiser-k": "Operations, Risk & Research",
    "linder-e": "Operations, Risk & Research", "love-p": "Operations, Risk & Research",
    "mclaughlin-e": "Operations, Risk & Research", "merriss-s": "Operations, Risk & Research",
    "meyers-a": "Operations, Risk & Research", "rodrique-r": "Operations, Risk & Research",
    "salisbury-h": "Operations, Risk & Research", "semperger-c": "Operations, Risk & Research",
    "solberg-g": "Operations, Risk & Research", "stokley-c": "Operations, Risk & Research",
    "symes-k": "Operations, Risk & Research", "white-s": "Operations, Risk & Research",

    # --- Executive & Corporate ---
    "buy-r": "Executive & Corporate", "delainey-d": "Executive & Corporate",
    "kitchen-l": "Executive & Corporate", "lavorato-j": "Executive & Corporate",
    "lay-k": "Executive & Corporate", "shankman-j": "Executive & Corporate",
    "skilling-j": "Executive & Corporate", "whalley-g": "Executive & Corporate",
    "zipper-a": "Executive & Corporate",
}

# Best guesses worth verifying before treating as labels.
LOW_CONFIDENCE = {
    "arora-h", "carson-m", "griffith-j", "lucci-p", "ward-k", "hodge-j",
    "panus-s", "bailey-s", "hain-m", "scott-s", "donoho-l", "hyatt-k",
    "hernandez-j", "rodrique-r", "stokley-c", "love-p", "zipper-a",
    "shankman-j", "buy-r", "mccarty-d",
}

# Keywords used to suggest a team for unmapped custodians (lowercase, matched as words).
TEAM_KEYWORDS = {
    "Trading": ["mmbtu", "basis", "henry hub", "position", "p&l", "bid", "offer",
                "enrononline", "curve", "spread", "mw", "palo verde", "sp15", "trader"],
    "Legal": ["isda", "agreement", "draft", "counterparty", "guaranty", "execution",
              "confidentiality", "termination", "amendment", "privileged", "attorney"],
    "Gov & Regulatory Affairs": ["ferc", "cpuc", "legislation", "legislature", "governor",
                                 "deregulation", "senate", "testimony", "lobby", "davis"],
    "Pipelines (ETS)": ["transwestern", "northern natural", "pipeline", "tariff",
                        "capacity", "throughput", "compressor", "rate case", "ets"],
    "Operations, Risk & Research": ["schedule", "nomination", "deal number", "checkout",
                                    "confirm", "settlement", "var", "model", "option pricing",
                                    "volatility", "research"],
    "Executive & Corporate": ["board", "prc", "reorganization", "announcement", "dynegy",
                              "shareholder", "strategy", "officers", "bankruptcy"],
}

MSGID_RE = re.compile(rb"^Message-ID:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
HEADER_SPLIT = re.compile(rb"\r?\n\r?\n")


def iter_email_files(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.startswith("."):
                continue
            yield os.path.join(dirpath, name)


def read_email(path, max_bytes=200_000):
    with open(path, "rb") as f:
        data = f.read(max_bytes)
    parts = HEADER_SPLIT.split(data, maxsplit=1)
    header = parts[0]
    body = parts[1] if len(parts) > 1 else b""
    m = MSGID_RE.search(header)
    msgid = m.group(1).strip() if m else None
    return msgid, header, body


def keyword_scores(text):
    text = text.lower()
    scores = {}
    for team, words in TEAM_KEYWORDS.items():
        scores[team] = sum(len(re.findall(r"\b" + re.escape(w) + r"\b", text)) for w in words)
    return scores


def process_custodian(path, dedup, sample_for_keywords):
    raw = 0
    seen = set()
    unique = 0
    kw_text = []
    for fpath in iter_email_files(path):
        raw += 1
        try:
            msgid, header, body = read_email(fpath)
        except OSError:
            continue
        key = msgid or fpath.encode()
        if dedup and key in seen:
            continue
        seen.add(key)
        unique += 1
        if sample_for_keywords and len(kw_text) < 500:
            subj = re.search(rb"^Subject:(.*)$", header, re.IGNORECASE | re.MULTILINE)
            kw_text.append((subj.group(1) if subj else b"") + b" " + body[:2000])
    text = b" ".join(kw_text).decode("utf-8", errors="ignore") if kw_text else ""
    return raw, unique, text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maildir", help="Path to the CMU maildir folder (contains allen-p, arnold-j, ...)")
    ap.add_argument("--out", default="enron_team_output", help="Output directory")
    ap.add_argument("--no-dedup", action="store_true", help="Count raw files instead of unique Message-IDs")
    args = ap.parse_args()

    custodians = sorted(
        d for d in os.listdir(args.maildir)
        if os.path.isdir(os.path.join(args.maildir, d)) and not d.startswith(".")
    )
    if not custodians:
        raise SystemExit(f"No custodian folders found in {args.maildir}")

    os.makedirs(args.out, exist_ok=True)
    rows, unassigned = [], []
    team_custodians = defaultdict(list)
    team_raw, team_unique = Counter(), Counter()

    for i, c in enumerate(custodians, 1):
        mapped = c in TEAM_MAP
        print(f"[{i}/{len(custodians)}] {c}", flush=True)
        raw, unique, text = process_custodian(
            os.path.join(args.maildir, c), dedup=not args.no_dedup, sample_for_keywords=not mapped
        )
        if mapped:
            team = TEAM_MAP[c]
            source = "manual-low-confidence" if c in LOW_CONFIDENCE else "manual"
        else:
            scores = keyword_scores(text)
            best = max(scores, key=scores.get) if any(scores.values()) else "Unknown"
            team = f"UNASSIGNED (suggest: {best})"
            source = "keyword-suggestion"
            unassigned.append({"custodian": c, "suggested_team": best,
                               **{f"score_{t}": scores[t] for t in TEAMS}})
        rows.append({"custodian": c, "team": team, "source": source,
                     "raw_files": raw, "unique_emails": unique})
        bucket = team if mapped else "Unassigned"
        team_custodians[bucket].append(c)
        team_raw[bucket] += raw
        team_unique[bucket] += unique

    with open(os.path.join(args.out, "custodian_counts.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["custodian", "team", "source", "raw_files", "unique_emails"])
        w.writeheader()
        w.writerows(rows)

    total_unique = sum(team_unique.values()) or 1
    with open(os.path.join(args.out, "team_summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["team", "n_custodians", "raw_files", "unique_emails", "pct_unique", "custodians"])
        for t in TEAMS + ["Unassigned"]:
            if t not in team_custodians:
                continue
            w.writerow([t, len(team_custodians[t]), team_raw[t], team_unique[t],
                        f"{100 * team_unique[t] / total_unique:.1f}", " ".join(team_custodians[t])])

    with open(os.path.join(args.out, "unassigned.csv"), "w", newline="") as f:
        fields = ["custodian", "suggested_team"] + [f"score_{t}" for t in TEAMS]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(unassigned)

    print("\nTeam summary (unique emails):")
    for t in TEAMS + ["Unassigned"]:
        if t in team_custodians:
            print(f"  {t:<30} {len(team_custodians[t]):>3} custodians  {team_unique[t]:>8,} emails")
    print(f"\nWrote results to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
