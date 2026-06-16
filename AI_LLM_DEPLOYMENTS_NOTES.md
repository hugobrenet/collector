# AI LLM Deployments Notes

## Goal

Move from hardcoded public LLM model configuration to an admin-managed LLM
catalog. The Collector should not ship with active public providers by default.
Administrators define which LLM deployments are available, and regular users
only choose from those approved deployments.

## Current Behavior

- The user configuration page shows a hardcoded list of models.
- The backend maps each selected model to:
  - provider
  - base URL
  - model name
- Users provide their own API key.
- The Collector returns the resolved LLM profile to the gateway through
  `/ai/llm/config`.
- The gateway remains responsible for LLM orchestration and MCP calls.

## Target Behavior

- No LLM deployment is active by default.
- If no deployment is configured, the user LLM config page shows an empty state:
  "No AI model is available. Contact an administrator."
- Collector administrators create and enable LLM deployments.
- Regular users select one enabled deployment and provide an API key only when
  required by that deployment.
- Users do not directly configure provider adapters, base URLs, or internal
  gateway endpoints.

## Terminology

Use "LLM deployment" or "admin-managed LLM profile" rather than only "model".
A deployment is more than a model name. It is:

- provider adapter
- base URL
- model name
- auth mode
- enabled/disabled state
- display label
- optional shared secret or policy fields

Example:

```json
{
  "name": "company-gpt53-codex",
  "label": "GPT-5.3 Codex",
  "provider_adapter": "openai_compatible",
  "base_url": "https://llm-gateway.example/usecase/35/providers/openai/models/gpt-5.3-codex/openai/v1",
  "model": "gpt-5.3-codex",
  "auth_mode": "user_api_key",
  "enabled": true
}
```

## Recommended Data Model

Admin table:

```text
ai_llm_deployment
- id
- name                 stable unique slug
- label                user-facing name
- provider_adapter     openai_compatible, anthropic, later mistral/gemini/etc
- base_url             public provider URL or company gateway URL
- model                model string sent to the provider
- auth_mode            user_api_key, shared_api_key, no_api_key
- api_key              encrypted shared key, nullable
- enabled              boolean
- sort_order           integer
- created
- updated
```

User table evolution:

```text
ai_llm_user_config
- user_id
- deployment_id
- api_key              encrypted user key, nullable
- updated
```

The current user table has provider/base_url/model fields. Those can be kept for
compatibility during migration, but the target shape should make deployment_id
the source of truth.

## Auth Modes

`user_api_key`

Each user provides a personal API key. This fits public providers and many
enterprise gateways that issue per-user tokens.

`shared_api_key`

The admin stores a shared API key on the deployment. Users do not see or edit
that key. The Collector returns it to the gateway only after resolving the
selected deployment.

`no_api_key`

The deployment requires no user key. This fits internal gateways authenticated
by network policy, mTLS, reverse proxy identity, or another server-side
mechanism.

## User UI

Regular user page:

- Show only enabled deployments.
- Show a deployment select field using the deployment label.
- Show the API key input only if the selected deployment uses `user_api_key`.
- Do not show base URL, provider adapter, internal endpoint, or shared key.
- If no deployment is enabled, show an empty state and disable save.

## Admin UI

Admin page:

- List deployments with enabled status and auth mode.
- Create/edit deployment.
- Validate required fields based on auth mode.
- Mask stored shared API keys.
- Allow disabling a deployment without deleting it.
- Optional later: duplicate deployment, test connection, sort order.

## Admin Templates

Provide a few static UI templates to help administrators create deployments.
Templates are not persisted, not active, and not visible to regular users. They
only prefill the admin form.

Rule:

```text
Template = static UI helper
Deployment = persisted admin configuration
Enabled deployment = visible user choice
```

Suggested templates:

- OpenAI public API
- Anthropic public API
- Custom OpenAI-compatible gateway

A template can prefill:

- provider_adapter
- base_url
- completion_token_parameter
- default auth_mode
- example model names

The admin must still save a deployment explicitly before anything is stored in
the database. A saved deployment must still be enabled before users can select
it.

This keeps the open source project neutral: public providers can be easy to set
up, but no provider is active by default.

## Collector to Gateway Contract

Keep the gateway contract stable. The Collector should resolve the selected
user deployment and return the same LLM profile shape as today:

```json
{
  "provider": "openai_compatible",
  "base_url": "https://...",
  "model": "gpt-5.3-codex",
  "api_key": "...",
  "system_prompt": "...",
  "temperature": null,
  "max_tokens": null,
  "completion_token_parameter": "max_completion_tokens",
  "max_tool_iterations": 5,
  "tool_result_max_chars": 20000
}
```

The gateway should not need to know whether the URL is a public provider or an
enterprise LLM gateway.

## Security Position

- Do not allow regular users to enter arbitrary base URLs.
- Avoid active public providers by default in the open source project.
- Encrypt both user API keys and shared deployment API keys.
- Never expose API keys, base URLs marked internal, or shared secrets in regular
  user responses.
- Keep the gateway as the only component that talks to providers.
- Continue using the existing state-changing confirmation guard in the gateway.

## Migration Plan

1. Introduce `ai_llm_deployment` table and admin helpers.
2. Add an admin page to create/list/edit/disable deployments.
3. Change user config page to select from enabled deployments.
4. Keep legacy hardcoded catalog only as non-active examples or remove it from
   runtime entirely.
5. Update `ai_llm_gateway_config()` to resolve user deployment to provider,
   base URL, model, and API key.
6. Preserve the existing gateway contract.
7. Add tests for:
   - no deployment configured
   - user_api_key deployment
   - shared_api_key deployment
   - no_api_key deployment
   - disabled deployment selected by existing user config
   - admin-only access to deployment management

## Open Questions

- Should deployments be global, group-scoped, or user-scoped later?
- Should the admin be able to override max tool iterations per deployment?
- Should deployments have a "test prompt" action in the admin UI?
- Should internal base URLs be hidden from all non-admin JSON responses?
- Should existing user configs be migrated automatically or treated as reset?

## Product Principle

The Collector admin defines the allowed AI surface. Users only select an
approved deployment and provide a secret when the deployment policy requires it.
This keeps the open source project neutral while supporting public providers,
enterprise gateways, and air-gapped installations.
