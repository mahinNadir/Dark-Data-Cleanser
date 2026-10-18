"""Phase 2 cleaning: strip quoted text, signatures, footers, URLs and emails.

    python src/clean.py            # writes a 20-email sample to inspect
    python src/clean.py --inspect  # checks what cleaning removes most (a few seconds)
    python src/clean.py --full     # cleans everything, prints stats, saves parquet
    python src/clean.py --filter   # drops/caps templated mass emails (needs --full first)
"""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

try:
    from tqdm import tqdm
except ImportError:          # progress bar is optional
    tqdm = None


ROOT = Path(__file__).resolve().parent.parent   # project root (parent of src/)

IN_PATH = ROOT / "data/interim/emails_deduped.parquet"
OUT_PATH = ROOT / "data/interim/emails_cleaned.parquet"
SAMPLE_PATH = ROOT / "data/interim/cleaning_sample.txt"
FILTERED_PATH = ROOT / "data/interim/emails_filtered.parquet"
INSPECT_EMPTY_PATH = ROOT / "data/interim/inspect_empty.txt"
INSPECT_LOW_PATH = ROOT / "data/interim/inspect_lowest_ratio.txt"

SAMPLE_SIZE = 20
SAMPLE_SEED = 7          # change to see a different 20 emails
MIN_CLEAN_CHARS = 20     # drop emails with less real text than this (full run only)

# --filter step. Patterns are matched against the lowercased subject with any
# leading Re:/Fw: removed. Edit these lists to taste, then run --filter again
# (it re-reads emails_cleaned.parquet, so it takes seconds).

# Machine-generated: no human wrote them, drop every one.
DROP_SUBJECTS = [
    r"^schedule crawler: hourahead failure",
    r"^trv notification",
    r"^warning:\s+your mailbox is approaching the size limit",
]

# Mass mailings / form letters: real text, but hundreds of near-identical copies
# would swamp the topics. Keep a random sample of at most N of each.
CAP_SUBJECTS = {
    r"^demand ken lay donate": 25,          # ~1,100 copies of one form letter
    r"^enron in action": 25,
    r"^enron mentions": 25,
    r"^williams energy news live": 25,
    r"^entouch newsletter": 25,
    r"^rigzone industry news": 25,
    r"^commissioner\.com e-reports": 25,
    r"^ethink about it": 25,
    r"^credit watch list": 25,
    r"^eol credit responses": 25,
    r"^weekend outage report": 25,
    r"^supplemental weekend outage report": 25,
    r"^power indices$": 25,
    r"^gas indices$": 25,
}


# Lotus Notes timestamp, e.g. "04/09/2001 04:35 PM"
NOTES_STAMP = r"\d{1,2}/\d{1,2}/\d{2,4}[ \t]+\d{1,2}:\d{2}[ \t]*[AP]M"

# Lotus Notes reply header: a "To:" line followed within a few lines by cc:/Subject:
NOTES_HEADER = re.compile(
    r"(?im)^[ \t]*To:[^\n]*(?:\n[^\n]*){0,6}?\n[ \t]*(?:cc|Subject):"
)

# The "Kate Symes   04/09/2001 04:35 PM" line (or name / stamp on two lines)
# that sits just above such a header and is left behind after cutting.
NOTES_RESIDUE = re.compile(
    r"(?i)(?:\n[ \t]*[^\n]{1,60}?[ \t]*" + NOTES_STAMP + r"[ \t]*"
    r"|\n[ \t]*[^\n]{1,40}\n[ \t]*" + NOTES_STAMP + r"[ \t]*)\s*\Z"
)

# Raw mail headers pasted into the body (inline forwards like "[Fwd: ...]").
RAW_HEADER_BLOCK = re.compile(
    r"\s*((?:[A-Za-z][A-Za-z0-9-]*:[^\n]*\n(?:[ \t]+[^\n]*\n)*)+)"
)
RAW_HEADER_NAMES = re.compile(
    r"(?im)^(?:Content-[\w-]+|Return-path|Received|MIME-version|Message-id|X-[\w-]+):"
)

# Signature-block detection (see strip_signature_block below).
# A line that looks like part of a signature: job title, company, street address, "City, ST 77002".
SIG_CUE = re.compile(
    r"(?i:\b(?:Vice President|President|Director|Manager|Analyst|Counsel|Trader|Associate|"
    r"Assistant|Executive|Specialist|Coordinator|Secretary|Attorney|Senior|Managing|VP)\b"
    r"|\b(?:Enron|ECT|Corp\.?|Inc\.?|LLC)\b)"
    r"|^\d+\s.*(?i:\b(?:street|st\.?|avenue|ave\.?|suite|floor|blvd|road)\b)"
    r"|,\s*[A-Z]{2}\s+\d{5}"
)
NAME_LINE = re.compile(r"[A-Z][A-Za-z'.-]+(?: [A-Z][A-Za-z'.-]+){1,3},?")  # "T.Jae Black"
DASHES = re.compile(r"-{2,}")                                              # "--" delimiter


# ASCII control characters except tab (9) and newline (10).
_ASCII_CTRL = {i: None for i in [*range(0, 9), *range(11, 32), 127]}


def remove_nonprintable(text):
    """Remove control/format characters, keeping newlines and tabs.

    Fast path for pure-ASCII text (most emails); the per-character Unicode
    check only runs for the few emails that contain non-ASCII characters.
    """
    if text.isascii():
        return text.translate(_ASCII_CTRL)
    return "".join(
        ch for ch in text
        if ch in "\n\t" or unicodedata.category(ch)[0] != "C"
    )


def strip_raw_headers(text):
    """Drop a block of raw mail headers at the very top of the body."""
    m = RAW_HEADER_BLOCK.match(text)
    if m and RAW_HEADER_NAMES.search(m.group(1)):
        return text[m.end():]
    return text


def cut_at_first(text, patterns):
    """Keep only the text before the earliest matching marker."""
    positions = []
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            positions.append(match.start())
    if positions:
        return text[:min(positions)]
    return text


def strip_signature_block(text, had_contact):
    """Remove a trailing name / title / company / address block (and a '--' delimiter).

    The block is the last run of non-blank lines, so it must sit after a blank line, be at
    most 8 lines, and every line at most 60 characters.
      - had_contact=True: a phone/fax/email block was just removed below it, so any short
        line that does not end like a sentence counts as signature.
      - otherwise every line must look like a name/title/company/address, and at least
        one must be a title, company or address.
    """
    lines = text.rstrip().split("\n")
    i = len(lines)
    while i > 0 and lines[i - 1].strip():      # contiguous non-blank lines at the end
        i -= 1
    block = [ln.strip() for ln in lines[i:]]
    if i == 0 or not 1 <= len(block) <= 8:
        return text
    if had_contact:
        strip = all(
            len(ln) <= 60
            and (not re.search(r"[.?!:,;]$", ln) or SIG_CUE.search(ln) or DASHES.fullmatch(ln))
            for ln in block
        )
    else:
        ok = all(
            len(ln) <= 60 and (DASHES.fullmatch(ln) or SIG_CUE.search(ln) or NAME_LINE.fullmatch(ln))
            for ln in block
        )
        strip = ok and len(block) >= 2 and any(SIG_CUE.search(ln) for ln in block)
    return "\n".join(lines[:i]).rstrip() if strip else text


def remove_signature(text):
    """Remove common trailing email signatures and contact blocks."""

    # Sign-off followed by a short signature-like block.
    signoff_pattern = (
        r"(?im)^[ \t]*"
        r"(?:Best regards|Kind regards|Regards|Sincerely|"
        r"Yours truly|Best wishes|Thank you|Thanks)"
        r"[,!]?[ \t]*\n"
        r"(?:(?:[ \t]*\n)|[ \t]*[^\n]{1,100}\n){0,3}"
        r"[ \t]*[A-Z][^\n]{0,80}(?:\n|$)"
    )

    # FIX 1: only cut at the LAST sign-off, and only if it is near the end.
    matches = list(re.finditer(signoff_pattern, text))
    if matches and len(text) - matches[-1].start() < 300:
        text = text[:matches[-1].start()]

    # Device-generated signatures ("Sent from my BlackBerry...", "Sent via BlackBerry by AT&T").
    text = re.sub(
        r"(?im)^[ \t]*(?:Sent (?:from my|via|wirelessly from my)|Get Outlook for)[ \t]*"
        r"(?:BlackBerry|iPhone|iPad|Android|iOS|Verizon|Cingular|AT&T|Palm|Treo|Nextel|"
        r"wireless|smartphone|mobile)\b.*$",
        "",
        text,
    )

    # FIX 2: trailing contact block, anchored to the true end of the text.
    # A line is a contact line if it is "<label> <number or email>", a bare phone
    # number, or a bare email.
    contact_line = (
        r"[ \t]*(?:"
        r"(?:Phone|Ph|Tel|Telephone|Fax|Mobile|Mob|Cell|Cel|Work|Home|Pager|Pgr|Voice|Direct|"
        r"Off|Office|Email|E-mail)\.?[ \t]*:?[ \t]*(?=[+(\d]|\S+@)[^\n]*"        # "Off. 713-..."
        r"|\+?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?:[ \t]*(?:x|ext\.?)[ \t]*\d+)?"   # bare number
        r"[ \t]*\(?(?:office|cell|fax|work|home|mobile)?\)?[ \t]*"
        r"|[\w.+-]+@[\w.-]+\.\w+[ \t]*"
        r")"
    )
    contact_pattern = (
        r"(?im)(?:\n[ \t]*)+" + contact_line + r"(?:\n" + contact_line + r")*\s*\Z"
    )
    before = text
    text = re.sub(contact_pattern, "", text)

    # The name / title / company lines that sit above the contact block.
    return strip_signature_block(text, had_contact=(text != before))


def clean_body(value):
    """Clean one email body while preserving its main message."""

    if pd.isna(value):
        return ""

    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ")      # non-breaking spaces defeat several rules below

    # Collapse long runs of blank lines up front. Some emails have thousands of
    # them, which makes the end-of-text regexes below very slow.
    text = re.sub(r"\n(?:[ \t]*\n){3,}", "\n\n\n", text)

    # Raw headers pasted at the top of the body (inline forwards).
    text = strip_raw_headers(text)

    # FIX 3: quote/reply markers re-added alongside the Outlook/Lotus ones.
    forwarded_markers = [
        r"(?im)^[ \t]*-{2,}[ \t]*Original Message\b[^\n]*$",   # also "Original Message Follows"
        r"(?im)^[ \t]*-{2,}[ \t]*Forwarded by\b.*$",
        r"(?im)^[ \t]*From:\s*.+@\s*(?:ECT|ENRON|HOU)\s+"
        r"\d{1,2}/\d{1,2}/\d{2,4}\s+"
        r"\d{1,2}:\d{2}\s*(?:AM|PM)\s*$",
        r"(?m)^[ \t]*>",                                  # quoted lines
        r"(?im)^[ \t]*On .{5,100} wrote:[ \t]*$",         # "On Mon, X wrote:"
        r"(?im)^[ \t]*From:[^\n]*\n[ \t]*Sent:[^\n]*\n",  # Outlook header block
    ]
    text = cut_at_first(text, forwarded_markers)

    # Lotus Notes quoted replies that have no "From:" line (To:/cc:/Subject: only).
    m = NOTES_HEADER.search(text)
    if m:
        text = NOTES_RESIDUE.sub("", text[:m.start()])

    # FIX 4: org banner left stranded above a cut Lotus Notes header.
    text = re.sub(
        r"(?i)(?:^|\n)[ \t]*Enron (?:North America Corp\.|Capital Management)"
        r"[ \t]*\s*\Z",
        "",
        text,
    )

    # Confidentiality notices and everything after them.
    footer_markers = [
        r"(?im)^[ \t|+]*This message may contain confidential\b.*$",
        r"(?im)^[ \t|+]*If you are not the addressee\b.*$",
        r"(?im)^[ \t|+]*This message (?:and any attachments )?"
        r"is confidential\b.*$",
        r"(?im)^[ \t|+]*CONFIDENTIALITY NOTICE\b.*$",
        r"(?im)^[ \t|+]*Disclaimer\s*:?.*$",
        # newsletter / list footers
        r"(?im)^[ \t]*(?:Powered by[^\n]{0,40}\n[ \t]*)?"
        r"(?:To unsubscribe|To be removed from|If you (?:wish|would like) to unsubscribe)\b.*$",
    ]
    text = cut_at_first(text, footer_markers)

    # Parsing/debug lines.
    text = re.sub(r"(?im)^[ \t]*PARSING FILE\s*-->>.*(?:\n|$)", "", text)

    text = remove_signature(text)

    # mailto links before ordinary URLs.
    text = re.sub(r"(?i)<?\bmailto:[^\s<>]+>?", "<EMAIL>", text)

    # Also swallow surrounding angle brackets so "<a@b.com>" becomes "<EMAIL>",
    # not "<<EMAIL>>".
    text = re.sub(
        r"<?\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b>?",
        "<EMAIL>",
        text,
        flags=re.IGNORECASE,
    )

    # Lotus Notes internal addresses have no ".com": "Kate Symes/HOU/ECT@ECT".
    text = re.sub(r"\b[\w.'-]+(?:/[A-Za-z]{2,})+@[A-Za-z]{2,}\b", "<EMAIL>", text)

    # Same bracket handling for URLs, so "<http://x.com>" becomes "<URL>", not "<<URL>>".
    text = re.sub(
        r"(?i)<?\b(?:https?://|www\.)[^\s<>]+>?",
        lambda m: "<URL>" + (
            m.group(0)[-1] if m.group(0)[-1] in ".,;:!?)" else ""
        ),
        text,
    )

    # Non-printable characters (keep newlines and tabs for now).
    text = remove_nonprintable(text)

    # FIX 5: separator lines (=====, -----, _____, etc.), before whitespace cleanup.
    text = re.sub(r"(?m)^[ \t]*[=\-_*+~#|]{5,}[ \t]*$", "", text)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def write_pairs(rows, path):
    """Write original and cleaned bodies of the given emails for reading by eye."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for index, row in rows.iterrows():
            original = "" if pd.isna(row.get("body")) else str(row["body"])
            f.write("=" * 80 + "\n")
            f.write(f"EMAIL {index}\n")
            f.write(f"Subject: {row.get('subject', '')}\n\n")
            f.write("--- ORIGINAL BODY ---\n" + original + "\n\n")
            f.write("--- CLEANED BODY ---\n" + clean_body(original) + "\n\n")

    print(f"Saved {len(rows)} emails to: {path}")


def write_sample(df):
    """Write a random sample of emails for manual inspection."""
    write_pairs(df.sample(n=min(SAMPLE_SIZE, len(df)), random_state=SAMPLE_SEED),
                SAMPLE_PATH)


def inspect(df, n=20000):
    """Check where cleaning removes the most, on a random sample of n emails.

    Shows (1) emails that became empty and (2) non-empty emails that lost the
    biggest share of their text. Those are where a rule that cuts too much
    would show up. Takes a few seconds; does not need the full run.
    """
    sample = df.sample(n=min(n, len(df)), random_state=SAMPLE_SEED).copy()
    sample["_clean"] = sample["body"].apply(clean_body)
    orig_len = sample["body"].fillna("").str.len()
    clean_len = sample["_clean"].str.len()

    print(f"Sample of {len(sample)} emails: "
          f"{(clean_len == 0).mean():.1%} empty, "
          f"{(clean_len < MIN_CLEAN_CHARS).mean():.1%} under {MIN_CLEAN_CHARS} chars")

    empty = sample[clean_len == 0]
    if len(empty):
        write_pairs(empty.sample(n=min(15, len(empty)), random_state=SAMPLE_SEED),
                    INSPECT_EMPTY_PATH)

    big = (clean_len > 0) & (orig_len >= 500)
    ratio = (clean_len / orig_len.clip(lower=1))[big]
    low = sample.loc[ratio.sort_values().head(15).index]
    write_pairs(low, INSPECT_LOW_PATH)

    print("\nLowest ratios among emails that kept some text (original >= 500 chars):")
    print(pd.DataFrame({
        "subject": low["subject"].str.slice(0, 60),
        "before": orig_len[low.index],
        "after": clean_len[low.index],
    }).to_string())


def clean_all(df):
    """Clean every email, print sanity stats, filter junk, write parquet."""
    df = df.copy()
    if tqdm is not None:
        tqdm.pandas(desc="Cleaning emails")
        df["clean_body"] = df["body"].progress_apply(clean_body)
    else:
        df["clean_body"] = df["body"].apply(clean_body)

    orig_len = df["body"].fillna("").str.len()
    clean_len = df["clean_body"].str.len()
    print(f"Rows in:               {len(df)}")
    print(f"Empty after cleaning:  {(clean_len == 0).sum()} "
          f"({(clean_len == 0).mean():.1%})")
    print(f"Avg chars before/after: {orig_len.mean():.0f} -> {clean_len.mean():.0f}")

    # Lowest after/before ratios among emails that kept some text. (Empty emails
    # all tie at 0, so they are left out here; --inspect shows those.)
    df["_ratio"] = clean_len / orig_len.clip(lower=1)
    keep_some = (clean_len > 0) & (orig_len >= 500)
    print("\nLowest length ratios, non-empty (check these by eye):")
    print(df[keep_some].sort_values("_ratio").head(10)[["subject", "_ratio"]].to_string())
    df = df.drop(columns="_ratio")

    # Templated mass emails (pipeline notices, schedule logs, newsletters) share a
    # subject once digits and Re:/Fw: prefixes are removed. Review this list and
    # add the ones you don't want to the filter below.
    template = (
        df["subject"].fillna("").str.lower()
        .str.replace(r"^(?:\s*(?:re|fw|fwd)\s*:\s*)+", "", regex=True)
        .str.replace(r"\d+", "#", regex=True)
        .str.strip()
    )
    print("\nMost repeated subject templates (candidates to filter):")
    print(template.value_counts().head(25).to_string())

    # Drop auto-generated log emails and near-empty results.
    auto = df["subject"].fillna("").str.match(r"Start Date: \d")
    print(f"\nAuto-generated schedule emails dropped: {auto.sum()}")
    df = df[~auto]
    short = df["clean_body"].str.len() < MIN_CLEAN_CHARS
    print(f"Dropped for under {MIN_CLEAN_CHARS} chars of text: {short.sum()}")
    df = df[~short]

    df["body"] = df["clean_body"]            # overwrite in place, so body keeps its position
    df = df.drop(columns=["clean_body"])     # original body is still in emails_deduped.parquet

    output_path = Path(OUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(output_path, index=False, compression="zstd")

    print(f"Rows out: {len(df)}")
    print(f"Saved to: {output_path}")


def filter_templates(df):
    """Drop machine-generated emails and cap mass mailings (see the lists at top)."""
    df = df.copy()
    df["_subj"] = (
        df["subject"].fillna("").str.lower()
        .str.replace(r"^(?:\s*(?:re|fw|fwd)\s*:\s*)+", "", regex=True)
        .str.strip()
    )
    n0 = len(df)

    print("Dropped (machine-generated):")
    for pat in DROP_SUBJECTS:
        hit = df["_subj"].str.contains(pat, regex=True)
        print(f"  {hit.sum():>7}  {pat}")
        df = df[~hit]

    # Shuffle first so each cap keeps a random (but reproducible) sample.
    df = df.sample(frac=1, random_state=SAMPLE_SEED)
    print("Capped (kept at most N of each):")
    for pat, cap in CAP_SUBJECTS.items():
        hit = df["_subj"].str.contains(pat, regex=True)
        over = hit & (hit.cumsum() > cap)
        print(f"  {over.sum():>7} removed of {hit.sum():>5} (cap {cap})  {pat}")
        df = df[~over]

    df = df.sort_index().drop(columns="_subj")   # back to original order
    print(f"\nRows: {n0} -> {len(df)}")
    return df


def run_filter():
    path = Path(OUT_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"{path.resolve()} not found. Run `python src/clean.py --full` first."
        )
    df = pd.read_parquet(path)
    print(f"Loaded {len(df)} cleaned emails from {path}\n")
    df = filter_templates(df)

    out = Path(FILTERED_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(out, index=False)
    print(f"Saved to: {out}")


def main():
    if "--filter" in sys.argv:        # works on the cleaned file, not the raw one
        run_filter()
        return

    input_path = Path(IN_PATH)
    if not input_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {input_path.resolve()}")

    df = pd.read_parquet(input_path)
    print(f"Loaded {len(df)} emails from {input_path}")

    if "--full" in sys.argv:
        clean_all(df)
    elif "--inspect" in sys.argv:
        inspect(df)
    else:
        write_sample(df)


if __name__ == "__main__":
    main()