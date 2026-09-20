# Security policy

## Supported version

Security fixes are prepared for the current `main` branch and the latest public
release tag. Older revisions are not maintained separately unless a written
support agreement says otherwise.

## Reporting a vulnerability

Do not open a public issue, pull request or discussion for a suspected
vulnerability.

Use this repository's **Security** tab and GitHub Private Vulnerability Reporting
when available. Otherwise, email
[security@openlegalcore.org](mailto:security@openlegalcore.org), preferably with
the subject `OpenLegalCore security report: Slovenian Legislation Pipeline`.

The project-wide reporting policy is published at
[openlegalcore.org/security](https://openlegalcore.org/security/).

Include only what maintainers need to reproduce the problem safely:

- affected version or commit;
- affected command or component;
- observed behavior, likely impact and required preconditions;
- a minimal synthetic reproduction;
- suggested remediation, if known; and
- a safe contact path for clarification.

Do not send PISRS credentials, DSNs, private endpoints, legislative text,
personal data, embedding input, checkpoints, database or vector snapshots, or
unredacted logs. Describe sensitive material first and wait for an agreed
exchange method.

Reports are reviewed privately and disclosure is coordinated after a safe fix or
mitigation is available. The project does not promise a response time and does
not operate a bug-bounty program.

## Scope

In scope are the application code, packaged artifacts, tracked deployment
templates, dependency lock, authorization gates, checkpoint and lock behavior,
deterministic identities, PostgreSQL and Qdrant integrity contracts, and
accidental disclosure through this repository.

PISRS availability or policy, embedding-provider services, operator-managed
PostgreSQL or Qdrant infrastructure, leaked operator credentials and downstream
applications are outside this repository's direct control. Reports that
demonstrate an application-level weakness at those boundaries are still welcome
through the private channel.

This policy does not authorize testing of private or third-party systems.

