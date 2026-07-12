# Security policy

TimeEcho handles identity, private conversations and uploaded media. Please do not disclose a suspected vulnerability in a public issue.

Report security problems privately to the repository maintainers and include the affected endpoint, reproduction steps and impact. Do not include real user messages, access tokens, SMTP credentials or production database exports.

The repository intentionally excludes environment files, signing keys, databases, uploaded media and generated APKs. Production deployments must generate independent JWT, encryption, server-salt, PostgreSQL and Redis secrets. Never reuse values from `.env.example`.

Supported security controls include hashed user and administrator passwords, revocable database sessions, rotating refresh tokens, one-time WebSocket tickets, authenticated private media, AES-GCM content encryption, administrator RBAC/audit logs and production startup validation.
