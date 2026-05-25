# Methodology

This document is for strategic reviewers. Engineering specification lives in
[`SPEC.md`](SPEC.md).

## The core claim

This prototype explores whether operating businesses like KFC Pakistan can be
modelled in a way that produces a different class of insight than what
conventional analytics platforms generate — and whether those insights can
serve as the data layer for new financial products.

The conventional framing of the problem is data fragmentation: POS lives in
one system, procurement in another, commissary in another. Solutions like
Dynamics 365 address this by integrating the sources into a unified data
layer. This integration is genuinely valuable. But integration alone does not
produce what this system attempts to produce.

The thing being attempted here is different. It is to model the operational
system as a set of **temporally-aligned streams that can be composed** —
meaning that events in one stream can be related to events in another stream
at corresponding moments in time, and the relationships across streams
themselves become queryable objects that persist, can be referenced, and can
be composed further.

## Three layers

1. **Data Layer** — observed real data, derived computations, and modelled
   synthetic flows, all temporally aligned, with provenance tagged on every
   value.
2. **Derived entities** — lineage-aware quantities computed from the data
   layer (e.g., supplier trust scores, working capital coefficients, demand
   predictability indices) that are stored and can be referenced by other
   computations.
3. **Credit products** — configurable templates that compose derived
   entities into financial instrument simulations.

The proof of architecture is **composability**: every number is decomposable
to its source events, and new derived entities and credit products can be
constructed from existing primitives.

## What this is not

The claim is *not* that conventional analytics platforms cannot produce any
of these insights with sufficient custom engineering. They likely can, with
effort. The claim is that this **architectural pattern** — data layer as
temporally-aligned streams, derived entities as persistent composable
quantities, credit products as templates over those entities — makes this
class of insight a standard output of the system, rather than something that
requires bespoke construction each time.

## What's real, what's synthetic

The numbers produced by this prototype are computed against substantially
synthetic data. They are directionally plausible but not actual reflections
of KFC Pakistan's operations.

- **Real (observed):** POS transactions from 34 KFC Pakistan stores, pulled
  from a live receiver. Menu items, store master, channel mix.
- **Derived:** ingredient consumption per store per day, computed from real
  POS × recipe BOM. Per-SKU margin chains. Per-supplier revenue exposure.
- **Modelled:** supplier master (15 suppliers; Big Bird Foods and K&N's Foods
  are real entities, others realistic placeholders). Procurement nodes —
  locations are real (Karachi commissary, cold/dry warehouses in Korangi),
  flows are modelled. Purchase orders, deliveries, invoices, payments —
  modelled with realistic cadence and variance.

The point of this prototype is not the specific numbers — it is the
methodology that produces them. When real procurement data eventually
replaces the modelled layer, the same methodology produces real numbers with
the same structure. The system is designed so that the data layer can be
swapped without architectural changes.

## Strategic ambition

If this works for KFC, the same methodology may transpose to other operating
assets — InDrive, other QSRs, broader SME populations. The output, if proven,
would be a credit underwriting layer that uses observed operational data —
addressing a gap that integrated-data platforms do not directly address.

A second deployment against a meaningfully different operating asset
(InDrive) is the proof point that this is methodology, not a one-off build.
That is the strategic ambition this v1 sets up.
