import os
from email.parser import BytesParser
from email import policy
import pandas as pd
from tqdm import tqdm
 
MAILDIR = "data/raw/maildir"
 
def parse_file(path, user, folder):
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)
    body = msg.get_body(preferencelist=("plain",))
    text = body.get_content() if body else ""
    return {
        "msg_id": msg["Message-ID"],
        "user": user,
        "folder": folder,
        "x_folder": msg["X-Folder"],
        "date": msg["Date"],
        "from": msg["From"],
        "to": msg["To"],
        "subject": msg["Subject"],
        "body": text,
    }
rows = []
for user in tqdm(os.listdir(MAILDIR)):
    user_dir = os.path.join(MAILDIR, user)
    for root, _, files in os.walk(user_dir):
        folder = os.path.relpath(root, user_dir)
        for fname in files:
            try:
                rows.append(parse_file(os.path.join(root, fname), user, folder))
            except Exception:
                pass  # log failures in a real run; a few are expected
 
df = pd.DataFrame(rows)
df.to_parquet("enron_emails.parquet", index=False)

print(len(df))
