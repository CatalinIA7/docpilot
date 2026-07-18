# Contributing to DocPilot

DocPilot favors small, reviewable changes that preserve its existing boundaries.
Open an issue before proposing a material feature or architecture change.

## Development Setup

```bash
git clone https://github.com/CatalinIA7/docpilot.git
cd docpilot
cp .env.example .env
docker compose up --build
```

Set a long development `JWT_SECRET_KEY`. A valid `OPENAI_API_KEY` is needed for
document embedding and AI-backed requests, but automated tests use fakes and must
never contact the provider.

## Branch and Commit Scope

- Branch from the latest `main`.
- Keep one concern per branch and pull request.
- Do not mix dependency, migration, deployment, monitoring, security, and
  documentation changes without a concrete reason.
- Preserve the static frontend; do not add Node/npm tooling for asset validation.
- Use focused conventional-style commit messages such as `fix:`, `feat:`,
  `security:`, `docs:`, or `chore:`.

## Required Validation

Run checks proportional to the change. Before requesting review, the normal full
set is:

```bash
docker compose config
docker compose build backend frontend
docker compose run --rm migrate alembic check
docker compose run --rm backend pytest
git diff --check
git status --short
```

Report exact test counts and warnings. Do not claim a GitHub Actions result until
the run has completed.

When application behavior changes, add focused tests. Preserve these invariants:

1. all document operations require authentication and ownership;
2. every question performs document retrieval;
3. conversation history does not replace retrieval;
4. message records do not store embeddings, retrieval scores, or prompt internals;
5. citations are reconstructed only from retrieved database chunks;
6. production schema changes are versioned through reviewed Alembic migrations.

## Pull Requests

Describe:

- the problem and smallest implementation;
- affected files and architecture decisions;
- environment or migration changes;
- tests, Docker, and manual checks actually performed;
- warnings, known limitations, and rollback considerations.

Never commit `.env`, credentials, uploaded documents, database files, virtual
environments, caches, logs, or generated test/build artifacts.

## Security Reports

Do not open a public issue containing credentials, access tokens, prompts,
uploaded documents, or exploit details. Report suspected vulnerabilities
privately to the repository owner through their GitHub profile contact channel.

## Documentation

Keep the README concise enough to scan and link detailed operational material in
`docs/`. Update commands and diagrams in the same pull request as the behavior or
topology they describe.
