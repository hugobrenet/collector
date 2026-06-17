import base64
import hashlib

from applications.init.modules.aconfig import config_get

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = Exception


DEFAULT_PROVIDER = "openai_compatible"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_COMPLETION_TOKEN_PARAMETER = "max_completion_tokens"
DEFAULT_MAX_TOOL_ITERATIONS = 5
DEFAULT_TOOL_RESULT_MAX_CHARS = 20000
API_KEY_ENCRYPTION_PREFIX = "fernet:v1:"

LLM_PROVIDER_ADAPTERS = [
    ("openai_compatible", "OpenAI-compatible"),
    ("anthropic", "Anthropic"),
]
LLM_AUTH_MODES = [
    ("user_api_key", "User API key"),
    ("shared_api_key", "Shared API key"),
    ("no_api_key", "No API key"),
]
LLM_COMPLETION_TOKEN_PARAMETERS = [
    ("max_completion_tokens", "max_completion_tokens"),
    ("max_tokens", "max_tokens"),
]


SYSTEM_PROMPT = (
    "You are an OpenSVC operations assistant. Be concise and factual. "
    "Use MCP tools only when live Collector data or an actual Collector action "
    "is needed. You can query OpenSVC infrastructure domains such as nodes, "
    "services, clusters, tags, apps, arrays, disks, compliance, and users. "
    "For general questions about who you are or what you can do, answer "
    "directly without searching tools. "
    "Never invent Collector data. If data is missing, ambiguous, or a tool "
    "fails, say so and ask for the missing identifier. "
    "For Collector actions, use only real MCP tools discovered with search_tools; "
    "do not invent API endpoints or substitute workflows. "
    "For state-changing tools, follow the selected tool schema and descriptions "
    "exactly, including confirmation fields when the schema requires them. Do "
    "not add a separate confirmation workflow from this prompt. "
    "If no suitable MCP tool exists, say the operation is unsupported and offer "
    "read-only analysis. Do not expose secrets, API keys, tokens, or internal "
    "implementation details."
)

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


def _strip(value):
    if value is None:
        return ""
    if isinstance(value, string_types):
        return value.strip()
    return str(value).strip()


def _api_key_encryption_secret():
    return _strip(config_get("ai_llm_api_key_encryption_key", ""))


def _fernet():
    secret = _api_key_encryption_secret()
    if secret == "":
        return None
    if Fernet is None:
        raise RuntimeError("cryptography is required to decrypt AI LLM API keys")

    secret_bytes = secret.encode("utf-8")
    try:
        return Fernet(secret_bytes)
    except Exception:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret_bytes).digest())
        return Fernet(key)


def ai_llm_api_key_is_encrypted(api_key):
    return _strip(api_key).startswith(API_KEY_ENCRYPTION_PREFIX)


def ai_llm_encrypt_api_key(api_key):
    api_key = _strip(api_key)
    if api_key == "" or ai_llm_api_key_is_encrypted(api_key):
        return api_key

    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("AI LLM API key encryption key is not configured")

    token = fernet.encrypt(api_key.encode("utf-8")).decode("ascii")
    return API_KEY_ENCRYPTION_PREFIX + token


def ai_llm_decrypt_api_key(api_key):
    api_key = _strip(api_key)
    if api_key == "" or not ai_llm_api_key_is_encrypted(api_key):
        return api_key

    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("AI LLM API key encryption key is not configured")

    token = api_key[len(API_KEY_ENCRYPTION_PREFIX):].encode("ascii")
    try:
        return fernet.decrypt(token).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("AI LLM API key can not be decrypted")


def _int_or_none(value):
    value = _strip(value)
    if value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_default(value, default):
    value = _int_or_none(value)
    if value is None:
        return default
    return value


def _choice_values(choices):
    return [item[0] for item in choices]


def _bool_value(value):
    if isinstance(value, string_types):
        return value.strip().lower() in ("1", "true", "t", "yes", "on")
    return bool(value)


def ai_llm_provider_choices():
    return list(LLM_PROVIDER_ADAPTERS)


def ai_llm_auth_mode_choices():
    return list(LLM_AUTH_MODES)


def ai_llm_completion_token_parameter_choices():
    return list(LLM_COMPLETION_TOKEN_PARAMETERS)


def ai_llm_user_row(db, user_id):
    q = db.ai_llm_user_config.user_id == user_id
    return db(q).select(db.ai_llm_user_config.ALL, limitby=(0, 1)).first()


def ai_llm_deployment_row(db, deployment_id, enabled_only=False):
    deployment_id = _int_or_none(deployment_id)
    if deployment_id is None:
        return None
    q = db.ai_llm_deployment.id == deployment_id
    if enabled_only:
        q &= db.ai_llm_deployment.enabled == True
    return db(q).select(db.ai_llm_deployment.ALL, limitby=(0, 1)).first()


def ai_llm_enabled_deployment_rows(db):
    q = db.ai_llm_deployment.enabled == True
    return db(q).select(
      db.ai_llm_deployment.ALL,
      orderby=(db.ai_llm_deployment.sort_order|db.ai_llm_deployment.label),
    )


def ai_llm_deployment_choices(rows):
    return [
      (str(row.id), row.label or row.name or str(row.id))
      for row in rows
    ]


def ai_llm_mask_api_key(api_key, visible=5):
    api_key = _strip(api_key)
    if api_key == "":
        return ""
    if len(api_key) <= visible:
        return "*" * len(api_key)
    return ("*" * (len(api_key) - visible)) + api_key[-visible:]


def ai_llm_form_defaults(row, deployment_rows=None):
    deployment_id = getattr(row, "deployment_id", None) if row is not None else None
    if deployment_id is None and deployment_rows:
        deployment_id = deployment_rows[0].id
    return dict(deployment_id=deployment_id)


def ai_llm_deployment_defaults(row=None):
    if row is None:
        return dict(
          name="",
          label="",
          provider_adapter=DEFAULT_PROVIDER,
          base_url="",
          model="",
          auth_mode="user_api_key",
          enabled=False,
          sort_order=0,
          completion_token_parameter=DEFAULT_COMPLETION_TOKEN_PARAMETER,
          max_tool_iterations=DEFAULT_MAX_TOOL_ITERATIONS,
          tool_result_max_chars=DEFAULT_TOOL_RESULT_MAX_CHARS,
        )
    return dict(
      name=row.name or "",
      label=row.label or "",
      provider_adapter=row.provider_adapter or DEFAULT_PROVIDER,
      base_url=row.base_url or "",
      model=row.model or "",
      auth_mode=row.auth_mode or "user_api_key",
      enabled=_bool_value(row.enabled),
      sort_order=row.sort_order or 0,
      completion_token_parameter=(
        row.completion_token_parameter or DEFAULT_COMPLETION_TOKEN_PARAMETER
      ),
      max_tool_iterations=row.max_tool_iterations or DEFAULT_MAX_TOOL_ITERATIONS,
      tool_result_max_chars=(
        row.tool_result_max_chars or DEFAULT_TOOL_RESULT_MAX_CHARS
      ),
    )


def ai_llm_store_values(db, vars, current_api_key=None):
    deployment = ai_llm_deployment_row(
      db,
      getattr(vars, "deployment_id", None),
      enabled_only=True,
    )
    if deployment is None:
        raise RuntimeError("Selected AI LLM deployment is not available")

    auth_mode = deployment.auth_mode or "user_api_key"
    api_key = None
    if auth_mode == "user_api_key":
        api_key = _strip(getattr(vars, "api_key", ""))
        if api_key == "":
            api_key = current_api_key
        api_key = ai_llm_encrypt_api_key(api_key)
        if _strip(api_key) == "":
            raise RuntimeError("An API key is required for this AI LLM deployment")
    elif auth_mode not in _choice_values(LLM_AUTH_MODES):
        raise RuntimeError("Unsupported AI LLM auth mode")

    return dict(
      deployment_id=deployment.id,
      api_key=api_key,
    )


def ai_llm_store_deployment_values(vars, current_api_key=None):
    provider_adapter = _strip(getattr(vars, "provider_adapter", ""))
    auth_mode = _strip(getattr(vars, "auth_mode", ""))
    completion_token_parameter = (
      _strip(getattr(vars, "completion_token_parameter", "")) or
      DEFAULT_COMPLETION_TOKEN_PARAMETER
    )

    if provider_adapter not in _choice_values(LLM_PROVIDER_ADAPTERS):
        raise RuntimeError("Unsupported AI LLM provider adapter")
    if auth_mode not in _choice_values(LLM_AUTH_MODES):
        raise RuntimeError("Unsupported AI LLM auth mode")
    if completion_token_parameter not in _choice_values(LLM_COMPLETION_TOKEN_PARAMETERS):
        raise RuntimeError("Unsupported completion token parameter")

    name = _strip(getattr(vars, "name", ""))
    label = _strip(getattr(vars, "label", ""))
    base_url = _strip(getattr(vars, "base_url", ""))
    model = _strip(getattr(vars, "model", ""))
    if not name or not label or not base_url or not model:
        raise RuntimeError("Name, label, base URL, and model are required")

    api_key = None
    if auth_mode == "shared_api_key":
        api_key = _strip(getattr(vars, "api_key", ""))
        if api_key == "":
            api_key = current_api_key
        api_key = ai_llm_encrypt_api_key(api_key)
        if _strip(api_key) == "":
            raise RuntimeError("A shared API key is required for this deployment")

    return dict(
      name=name,
      label=label,
      provider_adapter=provider_adapter,
      base_url=base_url,
      model=model,
      auth_mode=auth_mode,
      api_key=api_key,
      enabled=_bool_value(getattr(vars, "enabled", False)),
      sort_order=_int_or_default(getattr(vars, "sort_order", None), 0),
      completion_token_parameter=completion_token_parameter,
      max_tool_iterations=_int_or_default(
        getattr(vars, "max_tool_iterations", None),
        DEFAULT_MAX_TOOL_ITERATIONS,
      ),
      tool_result_max_chars=_int_or_default(
        getattr(vars, "tool_result_max_chars", None),
        DEFAULT_TOOL_RESULT_MAX_CHARS,
      ),
    )


def ai_llm_gateway_config(db, row):
    if row is None:
        return None

    deployment = ai_llm_deployment_row(db, row.deployment_id, enabled_only=True)
    if deployment is None:
        return None

    provider = deployment.provider_adapter or DEFAULT_PROVIDER
    base_url = _strip(deployment.base_url)
    model = _strip(deployment.model)
    if not base_url or not model:
        return None

    auth_mode = deployment.auth_mode or "user_api_key"
    if auth_mode == "user_api_key":
        api_key = ai_llm_decrypt_api_key(row.api_key)
        if _strip(api_key) == "":
            return None
    elif auth_mode == "shared_api_key":
        api_key = ai_llm_decrypt_api_key(deployment.api_key)
        if _strip(api_key) == "":
            return None
    elif auth_mode == "no_api_key":
        api_key = None
    else:
        raise RuntimeError("Unsupported AI LLM auth mode")

    return dict(
      provider=provider,
      base_url=base_url,
      model=model,
      api_key=api_key or None,
      system_prompt=SYSTEM_PROMPT,
      temperature=None,
      max_tokens=None,
      completion_token_parameter=(
        deployment.completion_token_parameter or DEFAULT_COMPLETION_TOKEN_PARAMETER
      ),
      max_tool_iterations=(
        deployment.max_tool_iterations or DEFAULT_MAX_TOOL_ITERATIONS
      ),
      tool_result_max_chars=(
        deployment.tool_result_max_chars or DEFAULT_TOOL_RESULT_MAX_CHARS
      ),
    )
