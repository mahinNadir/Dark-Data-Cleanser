# Enron Email Dataset: Division of Teams

The mailboxes in the CMU Enron maildir release are grouped into six teams based on each custodian's role at Enron. Folder names match the maildir (`lastname-firstinitial`).

Mailboxes marked with `*` are lower-confidence assignments and should be checked against signature lines and folder contents before they are used as ground-truth labels.

## 1. Trading (Gas & Power)

**Typical content:** positions and P&L, price curves, basis spreads, deal tickets, EnronOnline products, trader banter, and market color around California and Western power prices. Emails are short, informal, and jargon-heavy, full of hub names (Henry Hub, SoCal, PG&E Citygate, Palo Verde), volumes (MMBtu, MW), and dollar figures.

**Mailboxes:** allen-p, arnold-j, arora-h\*, badeer-r, bass-e, baughman-d, belden-t, benson-r, brawner-s, carson-m\*, crandell-s, cuilla-m, dorland-c, ermis-f, forney-j, gilbertsmith-d, griffith-j\*, grigsby-m, holst-k, keavey-p, kuykendall-t, lenhart-m, lucci-p\*, maggi-m, martin-t, may-l, mims-thurston-p, motley-m, neal-s, parks-j, platter-p, presto-k, quigley-d, reitmeyer-j, ring-a, ruscitti-k, saibi-e, scholtes-d, schwieger-j, shively-h, south-s, staab-t, stepenovitch-j, storey-g, sturm-f, swerzbin-m, tholt-j, thomas-p, townsend-j, tycholiz-b, ward-k\*, williams-w3, wolfe-j, zufferli-j

## 2. Legal

**Typical content:** ISDA master agreements, credit annexes, confidentiality agreements, turbine and construction contracts, counterparty approvals, redlined drafts sent as attachments, and privilege notices. Threads are long, formal, and attachment-heavy, using words like "draft," "execution copy," "counterparty," "guaranty," and "termination."

**Mailboxes:** bailey-s\*, cash-m, derrick-j, dickson-s, haedicke-m, heard-m, hodge-j\*, hyvl-d, jones-t, mann-k, nemec-g, panus-s\*, perlingiere-d, sager-e, sanders-r, shackleton-s, stclair-c, taylor-m

## 3. Government & Regulatory Affairs

**Typical content:** the California energy crisis, CPUC and FERC proceedings, deregulation strategy, legislative updates, press clippings, and talking points for lobbying. These mailboxes hold a very large number of forwarded news articles and distribution-list memos, so they are big but repetitive.

**Mailboxes:** dasovich-j, hain-m\*, kean-s, mara-s, shapiro-r, steffes-j

## 4. Pipelines / Enron Transportation Services (ETS)

**Typical content:** Transwestern and Northern Natural Gas operations, capacity sales, tariff filings, rate cases, scheduled outages, and budget and capex discussions. The tone is closer to engineering and regulated utilities than to trading, with vocabulary like "firm capacity," "throughput," "compressor," "tariff," and "FERC filing."

**Mailboxes:** blair-l, corman-s, donoho-l\*, fossum-d, geaccone-t, harris-s, hayslett-r, horton-s, hyatt-k\*, lokay-m, lokey-t, mccarty-d\*, mcconnell-m, schoolcraft-d, scott-s\*, watson-k

## 5. Operations, Risk & Research (Back / Middle Office)

**Typical content:** deal entry and checkout corrections, scheduling and nominations, confirmations, settlement discrepancies, risk reports, and systems issues. Kaminski's research group adds quantitative modeling, option pricing, PhD recruiting, and academic correspondence. Emails are highly templated and full of IDs, deal numbers, and spreadsheet attachments.

**Mailboxes:** beck-s, dean-c, farmer-d, gang-l, germany-c, giron-d, guzman-m, hernandez-j\*, kaminski-v, keiser-k, linder-e, love-p\*, mclaughlin-e, merriss-s, meyers-a, rodrique-r\*, salisbury-h, semperger-c, solberg-g, stokley-c\*, symes-k, white-s

## 6. Executive & Corporate Leadership

**Typical content:** organizational announcements, strategy, compensation and PRC reviews, board matters, and investor relations. In late 2001 it also covers the Dynegy merger, layoffs, and bankruptcy. The mix is broadcast memos, scheduling handled by assistants, and short directive emails. Executive mailboxes are thinner than others because assistants handled much of the correspondence.

**Mailboxes:** buy-r\*, delainey-d, kitchen-l, lavorato-j, lay-k, shankman-j\*, skilling-j, whalley-g, zipper-a\*

## Notes

- **Team boundaries blur.** Many custodians changed roles between 1999 and 2002, and traders, lawyers, and regulatory staff often appear on the same threads. Labeling by mailbox owner is cleaner than labeling individual emails, but expect cross-team content in every mailbox.
- **Shared noise appears in every team.** Company-wide announcements, newsletters, charity drives, fantasy football, and spam show up everywhere. Filter these out before using content to infer ownership.
- **Mailbox sizes are skewed.** Kaminski, Dasovich, Kean, and several legal mailboxes are much larger than the executive mailboxes, so stratify or downsample when training a classifier.
- **Coverage is partial.** About 120 of the roughly 150 custodians are assigned here. A few listed names may not appear in every release of the dataset.
