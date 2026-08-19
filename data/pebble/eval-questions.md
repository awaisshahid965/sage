---
doc_id: EVAL-001
title: Evaluation question set
version: 1.0
purpose: Ground truth for testing retrieval and answer quality
---

# Evaluation question set

Ground truth for the Pebble corpus. Each row gives the question, the correct
answer, and where the answer lives, so a retrieval hit can be scored
automatically and an answer can be graded against a known fact.

Categories:

- **plain** — one clause, one document. If these fail, retrieval is broken.
- **exception** — the general rule is wrong; the answer sits in an exception.
  Naive top-1 retrieval usually returns the general rule and looks confident.
- **multi-hop** — needs two or more documents combined.
- **confusable** — a very similar-looking wrong answer exists in the corpus.
- **arithmetic** — the corpus has the inputs, not the answer.
- **unanswerable** — the corpus does not contain this. Correct behaviour is to
  say so. These are the most valuable rows in the file.

---

## Plain

| # | Question | Expected answer | Source |
|---|---|---|---|
| P1 | How long do I have to return something? | 30 calendar days from delivery | POL-RET-001 §1 |
| P2 | Do you ship to Berlin? | Yes. Germany is on the EU standard service, 5–8 business days, €9.99, free over €150 | POL-SHP-003 §3 |
| P3 | What's the battery life of the Drift ANC? | 40 hours with ANC on, 55 with it off | CAT-PRD-004 §1 |
| P4 | When are you open on Sunday? | Closed. Email is not monitored either | POL-SUP-006 §1 |
| P5 | What's the dispatch cut-off? | 15:00 GMT on a business day | POL-SHP-003 §1 |
| P6 | How long is the warranty? | 24 months on devices | POL-WAR-002 §1 |
| P7 | Can I pay with Klarna? | Yes, UK and EU, orders £50–£1,000 for 3 instalments | POL-PAY-005 §1 |
| P8 | How long do you keep my order records? | 7 years, as a tax obligation | POL-PRV-007 §2 |

## Exception — the general rule is a trap

| # | Question | Expected answer | Wrong answer retrieval will find | Source |
|---|---|---|---|---|
| E1 | I opened my headphones and want to return them | 14 days, not 30. Hygiene restriction on opened audio | "30 days" from POL-RET-001 §1 | POL-RET-001 §2 |
| E2 | Can I return a gift card? | No. Gift cards are non-refundable and non-returnable, an explicit exception to the whole policy | The 30-day rule | POL-RET-001 §2, §7 |
| E3 | My Drift's battery is weak at 18 months. Is it covered? | No. Batteries carry 12 months, even though the device carries 24 | "24 months" | POL-WAR-002 §1 |
| E4 | I bought PebbleCare+ 24. Is my battery covered for 4 years? | No. PebbleCare+ extends the device period only, never the 12-month battery or 6-month accessory periods | "adds 24 months" | POL-WAR-002 §4 |
| E5 | I asked to be forgotten. Is everything deleted? | No. Account, marketing and support data are deleted; the transaction record is retained in restricted form for the remainder of 7 years | "right to erasure, 30 days" | POL-PRV-007 §2, §6 |
| E6 | I'm a student, can I get 10% off a Slate 11? | No. The student discount excludes Slate tablets. Education institutions get 5% | "Student 10%" | POL-PAY-005 §4 |
| E7 | Can I return a Pebble Renewed device? | Yes, standard 30-day window. But its warranty is 12 months, not 24 | Confusing the two periods | CAT-PRD-004 §7 |
| E8 | My battery is swelling and it's out of warranty | Urgent regardless of warranty status or age. Stop using and charging; Pebble collects at its own cost. Overrides every other policy | "out of warranty, not covered" | POL-SUP-006 §5 |
| E9 | I repaired my Drift myself with genuine parts. Void? | For devices released after Jan 2024, only the component worked on loses cover; the rest stands. Older devices void entirely | "any repair by anyone else voids all cover" | POL-WAR-002 §3 vs §8 |

## Confusable — a near-miss exists

| # | Question | Expected answer | The decoy | Source |
|---|---|---|---|---|
| C1 | How long until my refund arrives? | Up to 15 business days worst case: 5 to process plus 3–10 for a card | "5 business days" or "3–10 days" alone | POL-RET-001 §6 |
| C2 | Will I pay customs on delivery to Germany? | No. EU prices include duty and VAT. Refuse any carrier demand and contact support | Rest-of-world rules, where the customer *is* liable | POL-SHP-003 §3 vs §4 |
| C3 | I found it cheaper elsewhere on day 20 | Too late for price match, which is 14 days. But still inside the 30-day return window, so return and rebuy | "30 days" applied to price match | POL-PAY-005 §3 |
| C4 | Is the Drift ANC waterproof? | No water rating at all. Not rated for sweat or rain | Pods Pro and Track are IPX4 / 5 ATM | CAT-PRD-004 §1 vs §2, §4 |
| C5 | Does the Drift Lite work with a cable? | No, Bluetooth only. The Drift **ANC** has 3.5 mm and works with a flat battery | The ANC's wired mode | CAT-PRD-004 §1 |
| C6 | Does the Pebble Pen work with my Slate Mini? | No. Slate 11 only | "Pebble Pen — tablets" | CAT-PRD-004 §3, §6 |
| C7 | Can I price match against a marketplace seller? | No. Authorised UK retailers only; marketplace sellers explicitly excluded | The general price match promise | POL-PAY-005 §3 |
| C8 | I ordered Express Thursday at 4pm. Friday delivery? | No, Monday. After the 15:00 cut-off it dispatches Friday, and Express does not run at weekends | "Express = next business day" | POL-SHP-003 §1, §2 |

## Multi-hop

| # | Question | Expected answer | Needs |
|---|---|---|---|
| M1 | I'm returning an opened, working Drift ANC. What do I get back? | £211.65. It is over £200 and opened and not faulty, so the 15% restocking fee applies: £249 − £37.35 | CAT-PRD-004 §1 + POL-RET-001 §3 |
| M2 | Same question for a Drift Lite | Full £129. At or below £200, so no restocking fee | CAT-PRD-004 §1 + POL-RET-001 §3 |
| M3 | Can I get my Charge 27k shipped express to Australia? | No. It is 100 Wh, so it goes surface-only on air-restricted routes at rest-of-world timings, and the difference is refunded | CAT-PRD-004 §6 + POL-SHP-003 §5 |
| M4 | I want to close my account but I have store credit | Cannot close until credit is spent or the order concludes. Unspent credit is forfeited on closure and is not refunded to a card | POL-ORD-008 §6 |
| M5 | My parcel to Berlin is 16 business days late. What now? | Declared lost after 15 business days past the latest quoted date for the EU, so it qualifies: free reship or full refund, customer's choice | POL-SHP-003 §3, §7 |
| M6 | Agent wants to refund £400 on a returned Slate 11 | Requires a team lead. Agents are capped at £250 | CAT-PRD-004 §3 + POL-SUP-006 §3, §4 |
| M7 | My Drift needs a repair that'll take 12 days. Do I get a loan? | Yes. Over 10 business days and the order was over £300? No — the Drift is £249, so no loan device | CAT-PRD-004 §1 + POL-WAR-002 §6 |
| M8 | Same, but for a Slate 11 | Yes. £499 is over £300 and the repair exceeds 10 business days | CAT-PRD-004 §3 + POL-WAR-002 §6 |

M7 is deliberately shaped so the obvious answer is wrong. Both conditions must
hold and only one does.

## Arithmetic

| # | Question | Expected answer | Source |
|---|---|---|---|
| A1 | Bought a Drift ANC on 1 March 2025. When does battery cover end? | 1 March 2026 | POL-WAR-002 §1 |
| A2 | And device cover? | 1 March 2027 | POL-WAR-002 §1 |
| A3 | UK order of £45. Shipping cost? | £3.99. Free shipping starts over £50 | POL-SHP-003 §2 |
| A4 | Two Pods Pro, £179 each. Free UK shipping? | Yes, £358 is over £50 | CAT-PRD-004 §2 + POL-SHP-003 §2 |
| A5 | 15% restocking on a £499 Slate 11? | £74.85, refund £424.15 | POL-RET-001 §3 |

## Unanswerable — correct behaviour is to say so

These matter more than the rest of the file. A system that answers these is
hallucinating, and it will do it fluently.

| # | Question | Correct behaviour | Why it is tempting |
|---|---|---|---|
| U1 | When will order PB-4471 arrive? | Say the corpus has no order data; offer to look it up or ask for the reference | The format is real and shipping times are right there. This is the exact hallucination from Topic 2 |
| U2 | Where is my parcel right now? | Pebble cannot see location between carrier scans and should say so | Tracking is discussed at length in POL-SHP-003 §6 |
| U3 | How many employees does Pebble have? | Not in the corpus | Sounds like basic company info |
| U4 | Who is Pebble's CEO? | Not in the corpus | As above |
| U5 | Do you sell laptops? | **Answerable: no.** The catalogue states plainly that Pebble does not sell laptops, phones, TVs, cameras, or consoles | Looks unanswerable but is not. Tests over-refusal |
| U6 | What's the Drift ANC's warranty in Japan? | Warranty periods are not stated per territory; statutory rights vary. Should not invent a Japanese period | Warranty and shipping-to-Japan both exist separately |
| U7 | Can I get a refund on a 2021 purchase? | Policies carry effective dates from 2023 onward; the corpus does not cover 2021 terms | The 30-day rule is right there |
| U8 | What's the trade-in value of my iPhone? | Pebble accepts Pebble devices only; third-party devices are not accepted | Trade-in table looks generic |
| U9 | Does the Slate 11 have a headphone jack? | Not stated in the catalogue. Should not infer from other products | Every other spec is listed, so absence reads as an answer |
| U10 | What's your bank account number for a transfer? | Never supplied by an assistant. Bank transfer is business accounts only, arranged through an account manager | POL-PAY-005 §1 mentions bank transfer |

---

## Suggested scoring

**Retrieval.** For every row except the unanswerable ones, check whether the
named source document appears in the top-k chunks. Report recall@1, @3, @5.
The exception and confusable rows are where recall@1 collapses; that gap is
the number worth tracking.

**Answers.** Grade against the expected answer. Three outcomes are worth
separating rather than lumping into pass/fail:

- correct
- wrong, and the corpus contained the right answer — a retrieval or reasoning
  failure
- wrong, and the corpus did not contain it — a hallucination

**Refusal.** On the unanswerable rows, measure how often the system says it
does not know. Track over-refusal separately using U5, which *is* answerable —
a system tuned to refuse will fail that one, and refusing everything is not a
win.
