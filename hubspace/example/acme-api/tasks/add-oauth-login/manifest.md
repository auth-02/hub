# Add OAuth Login

## Context
Add third-party OAuth login (Google, GitHub) to the Acme API so users can sign in
without a password. This is demo content for the hub — no real data.

### Decisions
1. Use authorization-code flow with PKCE — captured 2026-06-15.
2. Store provider tokens encrypted at rest — captured 2026-06-15.

## Exploration Results
### Consumers / callers
The login page and the mobile client both hit `/auth/session`.

### Data shape / schema
Provider profile maps to the internal `users` table by email.

### Out of scope
SAML / enterprise SSO — separate task.

## Plan
- [x] Add provider config loader
- [x] Implement callback handler
- [ ] Wire refresh-token rotation

## Open questions
1. Which providers at launch? -> Google + GitHub.

## Testing plan
Unit tests per provider; one end-to-end happy path against a stub IdP.

## Rollout plan
Behind a feature flag; enable for staff first.

## Review
Pending.
