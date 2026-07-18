# Security Model and Operations

DocPilot handles account credentials, user documents, and requests to an external
AI provider. Its security model is intentionally small: authenticate every data
request, scope every database query to the authenticated owner, validate files
before parsing, expose only grounded citations, and fail closed when production
configuration is unsafe.

## Production Configuration

Set `DOCPILOT_ENVIRONMENT=production`. Backend startup then refuses to run when:

- `JWT_SECRET_KEY` is the development fallback or shorter than 32 characters;
- `DOCPILOT_CORS_ORIGINS` is missing, uses `*`/`null`, is not HTTPS, or includes
  URL paths, credentials, queries, or fragments;
- the trusted-host allowlist is missing or contains `*`.

Render supplies `RENDER_EXTERNAL_HOSTNAME`, which is automatically added to the
trusted-host list. Add comma-separated custom domains through
`DOCPILOT_TRUSTED_HOSTS`. Development retains explicit localhost, loopback, and
pytest `testserver` defaults.

OpenAPI, Swagger UI, and ReDoc are disabled in production. They remain available
in development at `/openapi.json`, `/docs`, and `/redoc`.

## Authentication and Authorization

- Passwords are hashed with pwdlib's recommended Argon2 implementation and are
  never logged or returned.
- Login performs one Argon2 verification even when an email is unknown, reducing
  account-enumeration timing differences. Login errors remain deliberately
  generic.
- Registration and login passwords are bounded at 128 characters to avoid
  password-hash resource abuse; registration requires at least 8 characters.
- JWTs use a fixed HS256 algorithm, include `sub`, `iat`, and `exp`, and require
  both `sub` and `exp` during decoding. Non-positive user IDs are rejected.
- `DOCPILOT_ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 1440 (24 hours). Changing
  the signing secret invalidates all existing tokens.
- Documents, chunks reached through documents, conversations, evaluation
  questions, runs, comparisons, and chat requests are scoped by the current
  user. Cross-user lookups return 404 rather than disclosing resource existence.

The application does not implement password reset, email verification, MFA,
refresh tokens, token revocation, or administrative roles. Those are explicit
limitations, not implicit guarantees.

## Upload Boundary

Upload validation is layered:

1. Normalize both POSIX and Windows path separators and retain only a bounded,
   printable display filename.
2. Accept only `.pdf` and `.docx` extensions.
3. Require the standard declared MIME type or `application/octet-stream` for
   command-line clients.
4. Read at most 10 MiB plus one byte and reject larger files.
5. Verify a PDF header within its first 1024 bytes.
6. Verify DOCX is a ZIP with `[Content_Types].xml` and `word/document.xml`.
7. Reject encrypted or path-traversing DOCX entries, more than 2,000 entries, or
   more than 50 MiB total uncompressed content.
8. Parse only after those checks pass; return generic parser/processing errors.
9. Store content under a generated UUID filename and re-check path containment
   before writes and deletes.

`DOCPILOT_MAX_REQUEST_SIZE` defaults to 11 MiB, leaving multipart overhead above
the 10 MiB file limit. The HTTP middleware rejects larger declared
`Content-Length` values before parsing. Requests without a declared length still
reach the route-level 10 MiB read limit; a public edge should also enforce a body
limit if chunked request resource abuse is a concern.

## HTTP and Browser Controls

The backend sends `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a restrictive
permissions policy. Production also sends HSTS and a JSON-compatible CSP.

The static frontend runs as UID 101 on unprivileged Nginx port 8080. It serves a
CSP limited to local scripts/styles/assets and HTTPS or local-development API
connections, denies framing, enables HSTS/nosniff/referrer/permissions headers,
and rejects non-GET/HEAD methods. Runtime API URL generation validates the scheme,
rejects control characters, and escapes JavaScript string metacharacters.

CORS permits only configured origins, `DELETE`, `GET`, `OPTIONS`, and `POST`, and
the `Authorization`, `Content-Type`, and `X-Request-ID` request headers. Cookies
are not used, so CORS credentials are disabled.

## Rate and Request Limits

Production enables a sliding-window in-memory limiter with independent per-client
defaults:

| Boundary | Variable | Default per minute |
| --- | --- | ---: |
| Registration and login | `DOCPILOT_AUTH_RATE_LIMIT_PER_MINUTE` | 20 |
| Document upload | `DOCPILOT_UPLOAD_RATE_LIMIT_PER_MINUTE` | 10 |
| Chat and provider-backed evaluation | `DOCPILOT_AI_RATE_LIMIT_PER_MINUTE` | 30 |

`DOCPILOT_RATE_LIMIT_ENABLED=false` preserves frictionless local tests and
development; the Render Blueprint sets it to `true`. Rejections return HTTP 429
and `Retry-After`.

The limiter is per process and intentionally has no new datastore dependency.
The current persistent-disk deployment is single-instance. Before scaling the
backend horizontally, replace it with a platform-edge or shared-store limiter.

## AI and Citation Integrity

Document text is explicitly marked as untrusted data in the system message.
Embedded instructions cannot alter application authorization, tools, storage, or
secrets; the provider receives only the current question, bounded conversation
context, and newly retrieved document chunks.

Every question still performs semantic retrieval. Conversation history does not
replace retrieval and does not store embeddings, prompt internals, or retrieval
scores. Model-provided source IDs are accepted only when they refer to a retrieved
source. The route then reconstructs page/paragraph/excerpt data from the actual
retrieved database chunk, so the provider cannot supply citation text or point to
another user's document.

Prompts and documents should still be treated as sensitive data sent to the
configured AI provider. The prompt boundary reduces instruction-following risk;
it cannot guarantee that every model response is correct.

## Dependencies and Containers

The security review upgraded the backend to Python 3.13.14 and patched releases
of FastAPI/Starlette, PyJWT, python-multipart, and pypdf. Direct dependencies are
pinned, including the OpenAI SDK and test tools. CI runs:

```bash
python -m pip install --disable-pip-version-check pip-audit==2.10.1
python -m pip_audit -r backend/requirements.txt --progress-spinner off
```

The pre-change audit on 2026-07-18 reported 57 known advisories across PyJWT,
python-multipart, pypdf, and Starlette. The post-change audit reported:

```text
No known vulnerabilities found
```

The backend and frontend runtime containers both use non-root users. A Docker
Scout scan was not performed because that client would export local image
metadata to an external service. This report does not claim an operating-system
vulnerability scan; base-image updates, non-root runtime checks, and normal image
build/smoke validation are the evidence available here.

## Secret and Log Handling

- `.env`, database files, uploads, virtual environments, caches, and logs are
  ignored and checked before commits.
- Render generates the JWT secret and prompts for the OpenAI key and exact CORS
  origin. Production values are not stored in Git.
- Structured logs omit credentials, authorization headers, prompts, questions,
  document content, original filenames, SQL/parameters, and raw exception text.
- Client-facing provider, parser, chunking, and evaluation errors are generic;
  operators correlate safe event types with `X-Request-ID`.

## Operator Checklist

1. Use `DOCPILOT_ENVIRONMENT=production`.
2. Generate a high-entropy JWT secret of at least 32 characters.
3. Set the exact HTTPS frontend origin and any exact custom backend hosts.
4. Keep the OpenAI key in platform secret storage and rotate it if exposed.
5. Keep rate limiting enabled and tune it from observed legitimate traffic.
6. Verify HSTS, CSP, Host rejection, CORS preflight, and `X-Request-ID` after
   deployment.
7. Run the dependency audit and rebuild both images during routine maintenance.
8. Review Render database/disk access, backups, and team permissions separately;
   repository code cannot enforce account-level platform policy.

Report suspected vulnerabilities privately to the repository owner. Do not put
credentials, access tokens, prompts, or uploaded documents in a public issue.
