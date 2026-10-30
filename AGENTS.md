# Agent instructions — PISRS ingest

**Scope:** only `OpenLegalCore/slovenia-pisrs-ingest`. Do not apply these rules to
the separate case-law repository or to other OpenLegalCore products.

**Development resumed:** the owner authorized continuation on 30 October 2026.
Proceed with the smallest concrete PISRS work item under this contract. This
authorization does **not** permit production writes, deployment, paid calls,
checkpoint/service changes or Git merges without their specific approval.

## Product and authority

Deliver **one small, reliable production PISRS ingester**, not a platform.
Completion requires evidence that legally accessible sources and their history
are represented in PostgreSQL, eligible text in Qdrant, and nightly updates
actually keep them synchronized. A patch, PR, test, release or package is not
the delivered product.

- [Linear product contract](https://linear.app/openlegalcore/document/pisrs-projektna-pogodba-source-to-index-completeness-9d8c57fb5c81):
  product scope and acceptance criteria.
- [Linear project](https://linear.app/openlegalcore/project/pisrs-complete-source-to-index-synchronization-b47e7deb7c78):
  the **only backlog** and place for measurements, history and decisions.
- This GitHub repository: code, PRs, CI and releases.
- [Official PISRS API](https://pisrs.si/swagger/navodila): external source contract.
- [README](README.md): operator and technical guidance;
  [CONTRIBUTING](CONTRIBUTING.md): contributions and CLA;
  [SECURITY](SECURITY.md): vulnerability reporting.

Do not duplicate detailed technical contracts, dated counts, issue inventories,
or release status in this file.

## Execution: shortest path to working data

1. Read the relevant existing Linear issue. Identify **one measured gap**
   between source, PostgreSQL, Qdrant, or actual nightly operation.
2. Apply the smallest safe correction to the **existing ingest**. Research or
   test only what is necessary to make that correction correct; reuse prior
   evidence. No generic audits, new platforms, speculative infrastructure
   work, unrelated refactors or unnecessary packaging.
3. Verify the specific change and required regressions. After an authorized
   deployment, verify its **actual data effect**, not merely CI or code state.
4. Report concisely: what works, what remains, and the single next action.
   Distinguish `PASS`, `FAIL` and `UNKNOWN` with dated evidence.

No subagents. Do not impose a special Codex command syntax (such as `/goal`)
when a normal task suffices. Never expand scope into case law, Engine/LWS,
`lexai-engine`, cross-project networking or firewall changes. Per the owner's
operational declaration, only PISRS ingest writes to `pisrs_current`;
do not invent competing writers without new evidence.

## Authorization and safety

Obtain explicit owner approval for the **specific operation** before bulk
authenticated source reads, production PostgreSQL/Qdrant mutations, paid
embeddings, `nightly`, backfill, `reconcile --apply`, deployment, Git merges,
or checkpoint, timer or service changes. Follow an approval through its stated
scope without artificial repeated confirmation. Do not rewrite Git history or
existing release tags.

For approved writes use only directly relevant safeguards (such as backup,
recovery, lock/preflight and readback); do not create a separate infrastructure
project. Never expose secrets, private DSNs or sensitive raw data; report secret
presence only as `SET`/`UNSET`.

Public code and documentation are in English; communicate with the owner in
Slovenian.
