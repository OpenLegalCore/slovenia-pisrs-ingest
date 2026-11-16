# OpenLegalCore PISRS staging on PIKI

PIKI is the planned permanent staging installation of the OpenLegalCore Slovenian legislation ingest. It archives authorized PISRS catalogues, legal text and observable history in PostgreSQL, then publishes an independently verified Qdrant index for the approved use case. The [staging master](docs/PIKI-PISRS-MASTER.md) defines scope, dependencies and acceptance.

This review candidate contains design and audit documents. The [environment](docs/PIKI-PISRS-ENV.md) and [API evidence](docs/PIKI-PISRS-API.md) distinguish verified observations from open requirements. Implementation begins after owner acceptance of G0–G2. The existing production release and source history remain available through [the historical v0.1.0 tag](https://github.com/OpenLegalCore/slovenia-pisrs-ingest/tree/v0.1.0).

OpenLegalCore is independent of the Slovenian government and PISRS operator. Use of this project is subject to [BUSL-1.1](LICENSE) and independent source access terms. See [Contributing](CONTRIBUTING.md) and the [security reporting policy](SECURITY.md).
