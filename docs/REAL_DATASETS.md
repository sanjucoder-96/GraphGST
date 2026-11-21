# Real GST Datasets — Research Catalog

*Phase 1 of the real-data validation effort. This is the "what data actually
exists" survey. It is written to be readable if you have never seen this project.*

Every dataset below was **fetch-verified** during research (we opened the page /
metadata / raw file and read it) unless a row says otherwise. We record what
each source **can and cannot prove** for Graph GST — we do not just pick the
first hit.

> Graph GST needs, at minimum, a **directed supplier → buyer edge** (who sold to
> whom) with **amounts** and ideally **dates** and **tax**, so it can build a
> graph, find cycles (circular trading), and reconcile invoices. Keep that
> shopping list in mind while reading.

---

## 0. The bottom line (read this first)

**Real, taxpayer-level GST invoice data is not publicly available, and legally
cannot be.** Individual invoices with real GSTINs, amounts, and supplier→buyer
links exist only inside GSTN / the IRP, behind per-taxpayer authentication.

- **CGST Act §158** forbids a public servant from disclosing the particulars in
  any return / statement / account furnished under the Act. Only **aggregate**
  data may be published.
- **CGST Act §158A** (Finance Act 2023) lets GSTN share return / e-invoice data
  **only** with notified government systems and **only with the taxpayer's
  consent** — a consent-gated pipe, the opposite of open data.
- **GSTN's data policy** keeps the data encrypted, India-localised, not for sale.

The only lawful public *taxpayer-level* surface is the GST portal's
**"Search Taxpayer"** lookup: you must already know a GSTIN and it returns
**registration metadata only** (legal name, state, status) — **no invoices, no
amounts, no counterparties, zero edges**. Everything else the government
publishes is **aggregate** (state × month revenue, filing counts).

So we do the honest thing: use the best **legally-usable analogs**, document
exactly what they miss, and state precisely what real data would be needed.

**Legend for the tables:** Y = yes · N = no · ~ = partial.
Columns: **Ent** = entity ids · **S→B** = supplier→buyer edge · **Inv** = invoice
ids · **Date** · **Tax** = tax amounts · **Ret** = GST returns · **IRN** =
e-invoice/e-way ids · **Lbl** = fraud/ring labels · **DL** = downloadable
without interactive auth.

---

## A. Official Indian government GST data — real, but **aggregate only**

These are genuinely official and free, and confirm the privacy wall: none of
them carries a GSTIN, an invoice, or a supplier→buyer edge.

| Dataset | Publisher | Records | Ent | S→B | Inv | Date | Tax | Lbl | DL | What it can prove |
|---|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| [GST Statistics portal](https://www.gst.gov.in/download/gststatistics) | GSTN | many .xlsx, FY17-27 | N | N | N | ~ | Y | N | Y | macro priors only (state × month) |
| [GST Collection (data.gov.in / Dept. of Revenue)](https://www.data.gov.in/keywords/gst) | Min. of Finance | ~21,039 rows | N | N | N | ~ | Y | N | Y (API key) | state/month collection totals |
| [GST Collection (Dataful mirror)](https://dataful.in/datasets/15167/) | Dataful (mirror) | 21,039 rows | N | N | N | ~ | Y | N | Y | same, convenient CSV/XLSX |
| [Net GST Revenue post-settlement (mirror)](https://dataful.in/datasets/18679/) | Dept. of Revenue | 8,547 rows | N | N | N | ~ | Y | N | Y | settlement revenue by state |
| [GST Council monthly releases](https://gstcouncil.gov.in/gst-revenue) | GST Council/PIB | 1 PDF/month | N | N | N | ~ | Y | N | N (PDF) | headline collection numbers |

**Can prove:** realistic macro distributions to *calibrate* a synthetic generator
or sanity-check aggregate anomaly. **Cannot prove:** anything about the graph —
no entities, no invoices, no edges, so **no reconciliation, no ring detection**.

---

## B. The one perfect shape — and why you can't have it

| Dataset | Ent | S→B | Inv | Date | Tax | Ret | IRN | Lbl | DL |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| [Transaction-level GSTR-1 / e-invoice IRN](https://einvoice.gst.gov.in/) | Y | **Y** | Y | Y | Y | Y | Y | N | **N** |

This is *exactly* what Graph GST wants — supplier GSTIN → recipient GSTIN,
invoice no + IRN, dates, CGST/SGST/IGST. But it is downloadable **only after
logging into the portal as that taxpayer**, for that taxpayer's own GSTIN, and
retained 6 months. It is **not a public dataset**, and collecting it broadly
would mean bypassing authentication — out of scope, full stop. This is the row
that defines what "authorized access" would unlock (see §F).

---

## C. GST-native structural analogs — downloadable, usable

Real or realistic transaction data with a genuine seller→buyer shape. None is
Indian taxpayer data, so none is confidential.

| Dataset | Publisher | Records | Ent | S→B | Inv | Date | Tax | Lbl | DL | License |
|---|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **[Iron Dealers](https://github.com/Sindhuja-5/circular-trade-detection)** | Indian commercial-tax research (anon.) | 130,535 tx / 799 dealers | ~ | **Y** | N | N | N | N | **Y (CSV)** | none (research use) |
| [B2B Sales Receipts](https://www.kaggle.com/datasets/walimuhammadahmad/receipt-data) | walimuhammadahmad | ~4.8 MB | **Y** | **Y** | Y | Y | **Y** | N | kaggle | Apache-2.0 |
| [Company Purchasing](https://www.kaggle.com/datasets/shahriarkabir/company-purchasing-dataset) | shahriarkabir | small | Y | **Y** | Y | Y | N | N | kaggle | CC0 |
| [Sales Data B2B (Quote→PO→DO)](https://www.kaggle.com/datasets/abhikol/sales-data-b2b) | abhikol | 5 tables | ~ | ~ | Y | Y | **Y** | N | kaggle | unclear |
| [Supply Chain (VAT)](https://www.kaggle.com/datasets/ayodejiibrahimlateef/supply-chain-datasets) | ayodejiibrahimlateef | 20k orders | Y | ~ | Y | Y | Y | N | kaggle | CC BY 4.0 |
| [GST Rates table](https://www.kaggle.com/datasets/prasad22/goods-and-service-tax-rates-dataset) | prasad22 | rate schedule | N | N | N | N | ~ | N | kaggle | CC0 |

**Iron Dealers** is the standout: it is a **real Indian commercial-tax
seller→buyer graph** built for *circular-trading* research — the exact domain —
and it downloads directly with no auth. Its price: only `Seller ID, Buyer ID,
Value` (no dates, no invoice ids, no tax, **no labels**), and dealer ids are
anonymised integers, not GSTINs. **Can prove:** ring detection + graph structure
on genuine tax data (unsupervised). **Cannot prove:** temporal, reconciliation,
ITC, or accuracy (no ground truth).

**B2B Sales Receipts** is the richest *invoice* analog (seller tax-id + buyer
tax-id + receipt id + dates + per-line 18% tax) — great for **reconciliation /
tax-amount** logic — but it is Pakistani NTN not Indian GSTIN, needs Kaggle auth,
and has no fraud labels.

---

## D. Labeled financial-crime graphs — ground truth for cycles

Not GST, but they carry **real fraud/ring labels**, which is the only way to get
honest precision/recall. Money-laundering "cycles" are a documented **analog** of
GST circular trading — related, not identical.

| Dataset | Publisher | Records | S→B | Date | Lbl | DL | License | Note |
|---|---|---|:--:|:--:|:--:|:--:|---|---|
| **[IBM AMLworld](https://github.com/IBM/AML-Data)** | IBM (NeurIPS'23) | 5.08 M tx | **Y** | Y | **Y (+ cycle typ.)** | **Y (HF)** | CDLA-Sharing-1.0 | best labelled directed graph incl. "simple cycle" |
| [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1) | ealaxi | 6.36 M tx | Y | ~ | Y | kaggle | CC BY-SA | labelled but *few cycles* (drain fraud) |
| [AMLSim](https://github.com/IBM/AMLSim) | IBM | configurable | Y | Y | **Y (Cycle typ.)** | Y (run it) | unclear | *generate* labelled rings |
| [GSTN Hackathon](https://github.com/Aakashdeep-Srivastava/GST-Hackathon) | GSTN | ~900k rows | **N** | N | Y | Y | unclear | real GST labels but **anonymised columns, no edges** |
| [Mexico SAT EFOS](https://arxiv.org/abs/2104.13353) | SAT/UNAM | ~10k labelled evaders | Y | Y | Y | **N** | proprietary | the ideal labelled invoice network — *not released* |

**IBM AMLworld** is the pick for the labelled/supervised path: directly
downloadable, commercial-clean, timestamps + amounts + a per-transaction
`Is Laundering` flag and a *simple-cycle* typology = ground-truth circular
trading. **Can prove:** the ring detector's *precision* on cycles, with real
labels, on data it did not generate. **Cannot prove:** GST-specific accuracy
(it's banking/AML) or general laundering recall (Graph GST only targets the
*cyclic* subset — by design).

The **GSTN Hackathon** set is the tantalising one — real GST fraud labels — but
its features are masked `Column0..Column21` with **no entities and no edges**, so
it can only feed a tabular classifier, never the graph. **Mexico SAT** is the
perfect labelled invoice network but is confidential government data.

---

## E. What we chose, and why

Two complementary datasets, mapping onto the two honest evaluation modes:

1. **Iron Dealers → real, UNSUPERVISED.** The closest thing to real GST data
   (genuine Indian commercial-tax seller→buyer graph, built for circular-trade
   research). No labels ⇒ we report *structure and candidates*, never accuracy.
2. **IBM AMLworld → labelled, SUPERVISED.** The strongest legally-usable labelled
   directed graph with a cycle typology ⇒ we report real *precision / recall /
   AUC*, with the "AML ≠ GST" caveat stated inline.

Both are implemented as adapters (`realdata/adapters/`). Neither is real taxpayer
data; the console shows a **PUBLIC DATASET** banner so nothing is mistaken for
real filings. See `docs/REAL_DATA_VALIDATION.md` for the measured results.

Rejected for the graph (documented so the choice is defensible): official
aggregates (no edges), GSTN Hackathon (no edges), single-sided invoice sets
(no seller), and the perfect-but-private GSTR-1/IRP data.

---

## F. What additional data would make this *properly* defensible

To validate GST circular trading on real Indian data, one legitimately-obtained
dataset with these fields is required (each row = one B2B invoice):

`supplier GSTIN, buyer GSTIN, invoice_no, invoice_date, taxable_value,
CGST, SGST, IGST, place_of_supply, HSN` — plus, ideally, the matching **GSTR-1
(outward)** and **GSTR-2B (inward)** records and **e-way bill / IRN** ids for
reconciliation and shared-transport signals, and if evaluation is the goal, a
**label** for known circular-trading rings.

The only lawful routes to that are: (a) a **taxpayer** exporting their own
GSTR-1/2B/e-invoice JSON and sharing it; (b) an **authorized data-sharing
arrangement** with a tax authority / GSP under §158A consent; or (c) a
**tax authority** running Graph GST inside their own environment. Graph GST's
`realdata/` adapter layer is built precisely so that, the day such access
exists, ingestion is a new adapter — not a re-architecture. See
`realdata/README.md` and `docs/REAL_DATA_VALIDATION.md`.
