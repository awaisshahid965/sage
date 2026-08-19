# Pebble corpus

Fictional policy documents for Pebble, the invented gadget store Sage answers
for. This exists to build and test retrieval against, not to be read.

Everything here is made up. There is no Pebble Ltd, no `pebble.example`, and no
real customer or order data anywhere in these files.

## Files

| File | Doc ID | What it holds |
| --- | --- | --- |
| `01-returns-and-refunds.md` | POL-RET-001 | Windows, exceptions, restocking fees, refund timing |
| `02-warranty-and-repairs.md` | POL-WAR-002 | Cover periods by component, exclusions, PebbleCare+, turnaround |
| `03-shipping-and-delivery.md` | POL-SHP-003 | Zones, times, costs, duty, lost parcels |
| `04-product-catalogue.md` | CAT-PRD-004 | SKUs, prices, specs, discontinued lines |
| `05-payments-pricing-promotions.md` | POL-PAY-005 | Methods, price match, codes, trade-in |
| `06-support-and-escalation.md` | POL-SUP-006 | Hours, authority limits, escalation routes |
| `07-privacy-and-data.md` | POL-PRV-007 | Collection, retention, rights, cookies |
| `08-order-lifecycle-and-accounts.md` | POL-ORD-008 | Order states, cancellation, accounts |
| `eval-questions.md` | EVAL-001 | Ground truth: questions, answers, source docs |

Each policy carries YAML front matter with a doc ID, version, and effective
date. Use those as chunk metadata so answers can cite a source and a version.

## Why it is shaped like this

A corpus of bland, non-overlapping prose will make your retrieval look far
better than it is. Every question has one obvious home, top-1 always hits, and
you learn nothing. These documents are built to fail in the ways real
documentation fails.

**Overlapping numbers that mean different things.** "30 days" is the return
window. "24 months" is the device warranty. "14 days" is opened audio *and*
price match *and* clearance returns. "3–5 business days" is UK shipping, and
"3–10 business days" is a card refund landing. A retriever matching on numbers
gets these confidently wrong.

**Answers that live in exceptions.** The general rule is stated first and
prominently, the exception later. Ask "can I return my headphones" and the
30-day clause is the strongest match, while the correct answer is a 14-day
hygiene restriction further down. This is the single most common real-world
RAG failure and roughly a third of the corpus is built around it.

**Facts split across documents.** Working out the refund on an opened Drift ANC
needs the price from the catalogue and the fee rule from the returns policy.
Neither document contains the answer.

**One deliberate internal tension.** POL-WAR-002 §3 says any third-party repair
voids cover; §8 narrows that for devices released after January 2024. The
documents resolve it explicitly, so a good system finds the resolution rather
than picking whichever it retrieved first.

**A policy that overrides all others.** A swelling battery is urgent regardless
of warranty age (POL-SUP-006 §5). Tests whether a system can let a safety
clause beat the clause it retrieved first.

**Things deliberately absent.** No order records, no customer data, no company
facts like headcount or leadership, no pre-2023 policy terms. These gaps are
the point: they are where hallucination shows up. `PB-4471` appears in the
corpus **only** as a format example, so "when will PB-4471 arrive" is
unanswerable by design — the same question from Topic 2.

**Structure that stresses chunkers.** Heavy tables in the catalogue and
warranty docs. Split a table mid-row and you get chunks where the header is
gone and the numbers are unattributable. Worth checking early.

## Using it

Chunk on headings first (`##` / `###`), since sections are self-contained and
numbered for citation. Keep the front matter as metadata on every chunk rather
than as chunk text.

Two things worth measuring from day one:

1. **Recall@k against `eval-questions.md`.** Every non-unanswerable row names
   its source document. Score the plain rows separately from the exception and
   confusable rows — the gap between them is the real signal, and the headline
   average hides it.
2. **Refusal rate on the unanswerable rows.** Then check U5 separately, which
   *is* answerable. A system tuned to refuse scores well on the first measure
   and fails U5. Refusing everything is not success.

## Consistency

Facts are consistent across documents except where a conflict is called out and
resolved in the text. If you find a contradiction that is not explicitly
flagged, it is a mistake in the corpus rather than a designed trap — worth
fixing, since an accidental contradiction teaches you nothing.

Anchor facts, repeated here so drift is easy to spot:

- return window 30 days; opened audio 14 days; gift cards never
- restocking 15%, only when opened **and** working **and** over £200
- warranty 24 months device, 12 months battery, 6 months accessory
- Renewed carries 12 months
- UK standard 3–5 days, free over £50; EU 5–8 days, free over €150
- EU prices include duty, rest of world does not
- Drift ANC £249, Drift Lite £129, Pods Pro £179, Slate 11 £499
- agent refund limit £250; loan device needs repair >10 days **and** order >£300
- order records kept 7 years, surviving erasure
