# Project goals

Improve the existing production PISRS ingest so required sources, text and history are
demonstrably complete and correctly represented in PostgreSQL and Qdrant.

| Priority | Existing issue | Work and completion criterion |
| --- | --- | --- |
| P1 | [OLC-77](https://linear.app/openlegalcore/issue/OLC-77) | Establish the active release, nightly execution, checkpoint and current data-integrity baseline; distinguish fresh evidence from older supplied audits. |
| P2 | [OLC-79](https://linear.app/openlegalcore/issue/OLC-79) | Verify official API contracts, identities and pagination; cover all seven state catalogs with reproducible coverage and regression evidence. |
| P3 | [OLC-80](https://linear.app/openlegalcore/issue/OLC-80) | Verify EU, municipal and Official Gazette sources, lawful access, text linkage and history, including 1991 onward and the March 2026 transition. |
| P4 | [OLC-85](https://linear.app/openlegalcore/issue/OLC-85) | Correct confirmed integrity/content faults with minimal changes, failure tests and measured effects. |
| P5 | [OLC-82](https://linear.app/openlegalcore/issue/OLC-82) | Measure and close historical gaps using a bounded, resumable and idempotent backfill; every exclusion has an evidence-backed reason. |
| P6 | [OLC-83](https://linear.app/openlegalcore/issue/OLC-83) | Pass source-to-storage acceptance and an approved deployment with verified rollback and postflight. |

P1 establishes evidence; P2/P3 establish source contracts; P4 implements proved corrections;
P5 closes measured historical gaps; P6 authorizes and verifies the resulting production release.
Independent safe work may proceed while host-only checks are pending.
OLC-78 supplies prior API research to P2; OLC-81 supplies prior EU/municipal research to P3.
OLC-84 is covered by these development documents. Retain these records without duplicate tasks.

## Starting evidence, 2026-10-31

- Reviewed public baseline: b2fd71f8568a36271607ce847d7f1a47325a1631.
- Source tree equals aa79194999ded54105274aec5cc0ac224799713f;
  this does not identify the currently installed production release.
- The unmodified baseline passed 39 offline tests in an isolated checkout.
- Source inspection finds four state-catalog calls plus /npb and /besedilo/{id};
  the three additional state catalogs and dedicated EU/municipal/Gazette ingestion are absent.
- A synthetic nested-HTML probe reproduced duplicate extraction of the same text.
- OLC-77/OLC-85 contain dated owner-supplied host findings. Revalidate their applicability
  against the installed release and state; do not present them as a newly executed audit.
- Current live source coverage, production runtime and full historical completeness are unknown.

Success is the verified ingest, not completion of documents or issue states.
