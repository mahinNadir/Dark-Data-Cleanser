#!/usr/bin/env python3
"""
Assigns Enron (CMU maildir release) custodians to six teams and counts emails per team.

Usage:
    python enron_teams.py /path/to/enron_mail_20150507.tar.gz   # no unzipping needed
    python enron_teams.py /path/to/maildir                      # or an extracted maildir
    python enron_teams.py <input> --no-dedup --out results/

The archive is read as a stream, one email at a time, so it never needs to be
extracted to disk.

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
import tarfile
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

# Best guesses to be verified before confirming as labels.
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
MAX_BYTES = 200_000


def iter_emails(source):
    """Yield (custodian, raw_bytes) for every email in a maildir folder or a .tar/.tar.gz archive."""
    if os.path.isdir(source):
        for c in sorted(os.listdir(source)):
            cdir = os.path.join(source, c)
            if c.startswith(".") or not os.path.isdir(cdir):
                continue
            for dirpath, _, filenames in os.walk(cdir):
                for name in filenames:
                    if name.startswith("."):
                        continue
                    try:
                        with open(os.path.join(dirpath, name), "rb") as f:
                            yield c, f.read(MAX_BYTES)
                    except OSError:
                        continue
    else:
        # "r|*" streams the archive sequentially without extracting anything
        with tarfile.open(source, mode="r|*") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                parts = member.name.split("/")
                idx = parts.index("maildir") + 1 if "maildir" in parts else 0
                if len(parts) <= idx + 1 or parts[idx].startswith("."):
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                yield parts[idx], f.read(MAX_BYTES)


def parse_email(data):
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Path to enron_mail_*.tar.gz (no extraction needed) or an extracted maildir folder")
    ap.add_argument("--out", default="enron_team_output", help="Output directory")
    ap.add_argument("--no-dedup", action="store_true", help="Count raw files instead of unique Message-IDs")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        raise SystemExit(f"Not found: {args.source}")

    raw = Counter()
    unique = Counter()
    seen = defaultdict(set)
    kw_text = defaultdict(list)
    n = 0
    for c, data in iter_emails(args.source):
        n += 1
        if n % 25000 == 0:
            print(f"  processed {n:,} files ({len(raw)} mailboxes so far)", flush=True)
        raw[c] += 1
        msgid, header, body = parse_email(data)
        if not args.no_dedup:
            key = msgid or f"{c}:{n}".encode()
            if key in seen[c]:
                continue
            seen[c].add(key)
        unique[c] += 1
        if c not in TEAM_MAP and len(kw_text[c]) < 500:
            subj = re.search(rb"^Subject:(.*)$", header, re.IGNORECASE | re.MULTILINE)
            kw_text[c].append((subj.group(1) if subj else b"") + b" " + body[:2000])
    seen.clear()

    custodians = sorted(raw)
    if not custodians:
        raise SystemExit(f"No mailboxes found in {args.source}")
    print(f"Done reading: {n:,} files across {len(custodians)} mailboxes")

    os.makedirs(args.out, exist_ok=True)
    rows, unassigned = [], []
    team_custodians = defaultdict(list)
    team_raw, team_unique = Counter(), Counter()

    for c in custodians:
        mapped = c in TEAM_MAP
        if mapped:
            team = TEAM_MAP[c]
            source = "manual-low-confidence" if c in LOW_CONFIDENCE else "manual"
        else:
            text = b" ".join(kw_text[c]).decode("utf-8", errors="ignore")
            scores = keyword_scores(text)
            best = max(scores, key=scores.get) if any(scores.values()) else "Unknown"
            team = f"UNASSIGNED (suggest: {best})"
            source = "keyword-suggestion"
            unassigned.append({"custodian": c, "suggested_team": best,
                               **{f"score_{t}": scores[t] for t in TEAMS}})
        rows.append({"custodian": c, "team": team, "source": source,
                     "raw_files": raw[c], "unique_emails": unique[c]})
        bucket = team if mapped else "Unassigned"
        team_custodians[bucket].append(c)
        team_raw[bucket] += raw[c]
        team_unique[bucket] += unique[c]

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