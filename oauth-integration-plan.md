# OAuth Integration Plan for CourtListener

## Motivation

CourtListener wants to deploy a **remote MCP server** that can be listed in
Anthropic's Connectors Directory and easily installed by users of Claude,
ChatGPT, and other LLM providers. The MCP specification (2025-03-26 and later)
**requires OAuth 2.1** for any HTTP-based remote MCP server. The current
token-based auth (DRF `TokenAuthentication`) does not satisfy this requirement.

---

## Current State

| Aspect | Status |
|---|---|
| API Auth | DRF TokenAuth, BasicAuth, SessionAuth |
| OAuth | **None** (only Zoho CRM integration, unrelated) |
| Rate Limiting | Per-user throttles via `ExceptionalUserRateThrottle` |
| CORS | `CORS_ALLOW_ALL_ORIGINS = True` for `/api/*`, GET/HEAD/OPTIONS only |
| MCP Server | In development at `courtlistener-api-client` repo; currently local-only (stdio), uses API tokens via env vars |
| MCP Help Page | Documents API-token auth; no OAuth flow described |

---

## What the MCP Spec Requires

Per the MCP authorization spec and Anthropic's Connector requirements:

1. **OAuth 2.1 Authorization Code flow with PKCE** (mandatory)
2. **Authorization Server Metadata** (`/.well-known/oauth-authorization-server`) — MCP clients MUST support this
3. **Protected Resource Metadata** (`/.well-known/oauth-protected-resource`) — servers SHOULD serve this (required in June 2025+ spec)
4. **Resource Indicators** (RFC 8707) — clients include `resource` param in token requests
5. **Dynamic Client Registration** (RFC 7591) — SHOULD support; was primary method until Nov 2025 spec
6. **Streamable HTTP transport** — required for remote MCP servers with Claude

### Anthropic Connector-Specific Requirements

- OAuth 2.0 Authorization Code flow where **Claude acts as the OAuth client**
- Callback URLs to allowlist: `https://claude.ai/api/mcp/auth_callback` and `https://claude.com/api/mcp/auth_callback`
- User consent screen (Claude user authorizes CourtListener access)
- Anthropic stores encrypted access/refresh tokens
- Test account for Anthropic reviewers
- Safety annotations on every tool

---

## Simplest Path: `django-oauth-toolkit`

### Why This Library

- **Mature, well-maintained** (Jazzband project, v3.2.0, supports Django 4.2–6.0)
- **PKCE required by default** — aligns with OAuth 2.1
- **Built-in DRF integration** — `oauth2_provider.contrib.rest_framework`
- **Supports all needed grant types**: Authorization Code, Client Credentials, Refresh Token
- **Provides all standard endpoints** out of the box: `/authorize/`, `/token/`, `/revoke/`, `/introspect/`
- **Dynamic Client Registration** support available
- **OpenID Connect** support if needed later
- Already used widely in Django projects with DRF

### What Needs to Be Built

The work breaks into **3 layers**: the OAuth provider on CourtListener, metadata
endpoints for MCP discovery, and updates to the remote MCP server itself.

---

## Implementation Plan

### Phase 1: Add OAuth 2.1 Provider to CourtListener

**Estimated scope: ~500-800 lines of new code + configuration**

#### 1.1 Install `django-oauth-toolkit`

```bash
uv add django-oauth-toolkit
```

#### 1.2 Configure Django Settings

```python
# cl/settings/third_party/oauth2.py (new file)

INSTALLED_APPS += ["oauth2_provider"]

OAUTH2_PROVIDER = {
    # OAuth 2.1 alignment
    "PKCE_REQUIRED": True,

    # Scopes matching existing API capabilities
    "SCOPES": {
        "read": "Read access to CourtListener data",
        "read:search": "Search case law, dockets, and oral arguments",
        "read:citations": "Look up cases by citation",
        "read:opinions": "Access opinion full text and metadata",
        "read:dockets": "Access docket information",
        "read:judges": "Access judge profiles",
        "read:courts": "Access court information",
    },
    "DEFAULT_SCOPES": ["read"],

    # Token settings
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,       # 1 hour
    "REFRESH_TOKEN_EXPIRE_SECONDS": 86400 * 30, # 30 days
    "ROTATE_REFRESH_TOKEN": True,

    # Security
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https"],
    "REQUEST_APPROVAL_PROMPT": "auto",  # Only prompt on first auth

    # Required grant types
    "ALLOWED_GRANT_TYPES": [
        "authorization-code",
        "refresh_token",
        "client-credentials",
    ],
}
```

#### 1.3 Add OAuth URLs

```python
# In cl/urls.py or a new cl/oauth/ app
urlpatterns += [
    path("o/", include("oauth2_provider.urls", namespace="oauth2_provider")),
]
```

This gives you out of the box:
- `GET /o/authorize/` — Authorization endpoint
- `POST /o/token/` — Token endpoint
- `POST /o/revoke_token/` — Token revocation
- `POST /o/introspect/` — Token introspection
- `GET /o/applications/` — Application management UI

#### 1.4 Add OAuth to DRF Authentication

```python
# cl/settings/third_party/rest_framework.py
"DEFAULT_AUTHENTICATION_CLASSES": (
    "oauth2_provider.contrib.rest_framework.OAuth2Authentication",  # NEW
    "rest_framework.authentication.BasicAuthentication",
    "rest_framework.authentication.TokenAuthentication",
    "rest_framework.authentication.SessionAuthentication",
),
```

This is **fully backwards-compatible** — existing token/session auth continues
to work. OAuth tokens are simply a new, additional auth method.

#### 1.5 Run Migrations

```bash
docker exec cl-django python manage.py migrate oauth2_provider
```

This creates tables for: `Application`, `AccessToken`, `RefreshToken`, `Grant`,
`IDToken`.

#### 1.6 Authorization Consent Template

Create a branded consent screen that Claude (or other LLM clients) will redirect
users to. django-oauth-toolkit provides a default template that can be
overridden:

```
cl/assets/templates/oauth2_provider/authorize.html
```

This should show:
- The requesting application name (e.g., "Claude by Anthropic")
- Requested scopes in plain language
- Approve/Deny buttons
- Link to CourtListener's terms of service

---

### Phase 2: MCP Discovery Metadata Endpoints

These are lightweight JSON endpoints that MCP clients use to discover how to
authenticate.

#### 2.1 Protected Resource Metadata

```
GET /.well-known/oauth-protected-resource
```

Returns:
```json
{
  "resource": "https://www.courtlistener.com",
  "authorization_servers": ["https://www.courtlistener.com"],
  "scopes_supported": ["read", "read:search", "read:citations", ...],
  "bearer_methods_supported": ["header"]
}
```

#### 2.2 Authorization Server Metadata (RFC 8414)

```
GET /.well-known/oauth-authorization-server
```

Returns:
```json
{
  "issuer": "https://www.courtlistener.com",
  "authorization_endpoint": "https://www.courtlistener.com/o/authorize/",
  "token_endpoint": "https://www.courtlistener.com/o/token/",
  "revocation_endpoint": "https://www.courtlistener.com/o/revoke_token/",
  "introspection_endpoint": "https://www.courtlistener.com/o/introspect/",
  "scopes_supported": ["read", "read:search", ...],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
  "registration_endpoint": "https://www.courtlistener.com/o/register/"
}
```

#### 2.3 Dynamic Client Registration (Optional but Recommended)

django-oauth-toolkit does not include DCR out of the box. Options:
- **Option A (simplest)**: Pre-register Claude as an OAuth application in
  CourtListener's admin. This is sufficient for the Connectors Directory since
  Anthropic provides a fixed client_id/secret.
- **Option B**: Implement a simple `/o/register/` endpoint that accepts
  RFC 7591 registration requests. This enables any MCP client to self-register.

**Recommendation**: Start with Option A. Pre-register known clients (Claude,
ChatGPT, etc.) and add DCR later if demand warrants it.

---

### Phase 3: Wire Up the Remote MCP Server

The MCP server lives in the `courtlistener-api-client` repo. Changes needed:

1. **Add Streamable HTTP transport** (in addition to existing stdio)
2. **Accept Bearer tokens** from OAuth flow instead of API tokens from env vars
3. **Return proper 401** with `WWW-Authenticate` header when unauthenticated
4. The MCP server proxies authenticated requests to CourtListener's API using
   the OAuth access token

This is largely independent of the CourtListener Django changes and can proceed
in parallel.

---

### Phase 4: Register with Anthropic Connectors Directory

1. Pre-register Claude as an OAuth application:
   - Client type: Confidential
   - Grant type: Authorization Code
   - Redirect URIs: `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback`
2. Create a test account for Anthropic reviewers
3. Add safety annotations to all MCP tools
4. Submit via Anthropic's Remote MCP Server Submission process

---

## Architecture Diagram

```
┌──────────────┐     ┌───────────────────────────────────────┐
│  Claude.ai   │     │         CourtListener                 │
│  (MCP Client)│     │                                       │
│              │     │  ┌─────────────────────────────┐      │
│  1. Discover ├────►│  │ /.well-known/oauth-*        │      │
│              │     │  │ (metadata endpoints)        │      │
│  2. Authorize├────►│  │                             │      │
│     (browser)│     │  │ /o/authorize/               │      │
│              │     │  │ (consent screen)            │      │
│  3. Token    ├────►│  │                             │      │
│     exchange │     │  │ /o/token/                   │      │
│              │     │  │ (OAuth2 token endpoint)     │      │
│              │     │  └─────────────────────────────┘      │
│              │     │                                       │
│  4. MCP calls├────►│  ┌─────────────────────────────┐      │
│  (Bearer tok)│     │  │ /mcp/ (Streamable HTTP)     │      │
│              │     │  │ Remote MCP Server           │      │
│              │     │  │ (validates OAuth tokens,    │      │
│              │     │  │  calls DRF API internally)  │      │
│              │     │  └─────────────────────────────┘      │
└──────────────┘     └───────────────────────────────────────┘
```

---

## Key Decision: Where Does the MCP Server Live?

Two options:

### Option A: MCP Server as a Separate Service (current plan)
- Lives in `courtlistener-api-client` repo
- Deployed as a separate process
- Proxies requests to CourtListener API
- Pro: Clean separation, can be pip-installed for local use too
- Con: Extra deployment, token forwarding complexity

### Option B: MCP Server Embedded in CourtListener Django
- Add MCP endpoints directly to the Django app (e.g., `/mcp/`)
- Use DRF + django-oauth-toolkit natively
- Pro: Single deployment, direct DB access, OAuth works natively
- Con: Couples MCP to the monolith, can't be pip-installed for local stdio use

**Recommendation**: **Hybrid approach**. Keep the `courtlistener-api-client`
package for local stdio MCP use, but add a thin Streamable HTTP MCP endpoint
inside CourtListener itself for the remote/Connector use case. This way:
- OAuth tokens are validated directly by django-oauth-toolkit (no token forwarding)
- The MCP endpoint has direct access to Django ORM (faster than proxying through REST)
- Local users still `uvx courtlistener-mcp` with API tokens
- The Connector points to `https://www.courtlistener.com/mcp/`

---

## Minimal Viable Implementation Checklist

- [ ] `uv add django-oauth-toolkit`
- [ ] Create `cl/settings/third_party/oauth2.py` with OAUTH2_PROVIDER config
- [ ] Add `oauth2_provider` to INSTALLED_APPS
- [ ] Add OAuth2Authentication to DRF auth classes
- [ ] Include `oauth2_provider.urls` in URL config
- [ ] Run migrations
- [ ] Create consent template (`oauth2_provider/authorize.html`)
- [ ] Add `/.well-known/oauth-authorization-server` endpoint
- [ ] Add `/.well-known/oauth-protected-resource` endpoint
- [ ] Pre-register Claude as an OAuth application (via admin or data migration)
- [ ] Add Streamable HTTP MCP endpoint at `/mcp/`
- [ ] Submit to Anthropic Connectors Directory

---

## What We Do NOT Need

- **No changes to existing API endpoints** — OAuth is additive
- **No user migration** — existing token auth continues to work
- **No new user model fields** — django-oauth-toolkit uses its own models
- **No OIDC** (yet) — pure OAuth 2.1 is sufficient for MCP
- **No dynamic client registration** (initially) — pre-register known clients

---

## Risks and Considerations

1. **Scope mapping**: Need to decide granularity of OAuth scopes vs. current
   all-or-nothing token auth. Starting with a simple `read` scope is fine.

2. **Rate limiting**: OAuth-authenticated requests should respect the same
   throttle infrastructure. `ExceptionalUserRateThrottle` already works per-user,
   so this should work automatically since OAuth tokens are tied to users.

3. **Token lifetime**: MCP spec expects refresh tokens. django-oauth-toolkit
   handles this natively with `ROTATE_REFRESH_TOKEN`.

4. **CORS**: Current CORS only allows GET/HEAD/OPTIONS. OAuth endpoints need
   POST. May need to extend CORS config for `/o/token/` at minimum.

5. **HTTPS enforcement**: OAuth 2.1 requires HTTPS. CourtListener already
   enforces HTTPS in production.

---

## Sources

- [MCP Authorization Spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization)
- [MCP Authorization Spec (Draft)](https://modelcontextprotocol.info/specification/draft/basic/authorization/)
- [Auth0: MCP Specs Update - All About Auth](https://auth0.com/blog/mcp-specs-update-all-about-auth/)
- [Stack Overflow: Authentication and Authorization in MCP](https://stackoverflow.blog/2026/01/21/is-that-allowed-authentication-and-authorization-in-model-context-protocol/)
- [Anthropic: Building Custom Connectors via Remote MCP](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Anthropic: Remote MCP Server Submission Guide](https://support.claude.com/en/articles/12922490-remote-mcp-server-submission-guide)
- [Anthropic: Connectors Directory FAQ](https://support.claude.com/en/articles/11596036-anthropic-connectors-directory-faq)
- [Claude Connector OAuth Authentication (sunpeak)](https://sunpeak.ai/blogs/claude-connector-oauth-authentication/)
- [django-oauth-toolkit Documentation](https://django-oauth-toolkit.readthedocs.io/en/latest/)
- [django-oauth-toolkit PKCE Tutorial](https://www.liip.ch/en/blog/authorization-code-with-pkce-on-django-using-django-oauth-toolkit)
- [Cloudflare: MCP Authorization](https://developers.cloudflare.com/agents/model-context-protocol/authorization/)
- [Stytch: MCP Auth Implementation Guide](https://stytch.com/blog/MCP-authentication-and-authorization-guide/)
- [MCP OAuth 2.1 Implementation Guide](https://www.mcpserverspot.com/learn/architecture/mcp-oauth-implementation-guide)
- [Aembit: MCP, OAuth 2.1, PKCE](https://aembit.io/blog/mcp-oauth-2-1-pkce-and-the-future-of-ai-authorization/)
