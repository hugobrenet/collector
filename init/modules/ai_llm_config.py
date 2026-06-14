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
LLM_MODEL_CATALOG = [
    {
      "model": "gpt-5-mini",
      "label": "OpenAI - GPT-5 mini",
      "provider": "openai_compatible",
      "base_url": DEFAULT_OPENAI_BASE_URL,
    },
    {
      "model": "gpt-5.2",
      "label": "OpenAI - GPT-5.2",
      "provider": "openai_compatible",
      "base_url": DEFAULT_OPENAI_BASE_URL,
    },
    {
      "model": "gpt-4.1-mini",
      "label": "OpenAI - GPT-4.1 mini",
      "provider": "openai_compatible",
      "base_url": DEFAULT_OPENAI_BASE_URL,
    },
    {
      "model": "gpt-4.1",
      "label": "OpenAI - GPT-4.1",
      "provider": "openai_compatible",
      "base_url": DEFAULT_OPENAI_BASE_URL,
    },
    {
      "model": "gpt-4o-mini",
      "label": "OpenAI - GPT-4o mini",
      "provider": "openai_compatible",
      "base_url": DEFAULT_OPENAI_BASE_URL,
    },
    {
      "model": "claude-sonnet-4-6",
      "label": "Anthropic - Claude Sonnet 4.6",
      "provider": "anthropic",
      "base_url": DEFAULT_ANTHROPIC_BASE_URL,
    },
    {
      "model": "claude-opus-4-6",
      "label": "Anthropic - Claude Opus 4.6",
      "provider": "anthropic",
      "base_url": DEFAULT_ANTHROPIC_BASE_URL,
    },
    {
      "model": "claude-sonnet-4-20250514",
      "label": "Anthropic - Claude Sonnet 4",
      "provider": "anthropic",
      "base_url": DEFAULT_ANTHROPIC_BASE_URL,
    },
]
SYSTEM_PROMPT = (
    "You are an OpenSVC operations assistant. Answer infrastructure questions "
    "using the OpenSVC MCP tools when live collector data is needed. Discover "
    "the available tools, search for the requested object, then call the most "
    "appropriate tool with valid arguments before giving a factual answer. "
    "Never invent node, service, cluster, or compliance information. If the "
    "tool data is missing, ambiguous, or returns an error, explain that clearly "
    "and ask for the missing identifier. Before calling any MCP tool that "
    "creates, updates, deletes, executes, or otherwise changes Collector state, "
    "first resolve and summarize the exact target objects and intended changes, "
    "then ask the user for an explicit confirmation in a new message. Do not "
    "call the state-changing tool in the same turn as the initial request or "
    "after only self-resolving identifiers. When the selected tool schema "
    "requires request.confirmation.phrase, generate a concise phrase, show it "
    "to the user, wait for the user to repeat it verbatim in a new message, "
    "then set request.confirmation.phrase to that exact phrase. For destructive "
    "actions, the confirmation must include the exact stable identifier required "
    "by the tool when one exists, such as a Collector node_id for node deletion. "
    "Never claim that a requested create, update, delete, rename, attach, detach, "
    "or migration workflow can be executed unless the required MCP tools are "
    "available and have been selected from tool search results. Do not invent "
    "Collector API endpoints or compose substitute workflows such as rename by "
    "create, reattach, and delete unless every required state-changing tool "
    "exists in MCP and the user confirms the full plan. If no suitable tool "
    "exists, say that the requested operation is not supported by the current "
    "MCP tool surface and limit yourself to read-only analysis. "
    "Do not "
    "expose secrets, API keys, tokens, or internal implementation details."
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
    return int(value)


def _float_or_none(value):
    value = _strip(value)
    if value == "":
        return None
    return float(value)


def _int_or_default(value, default):
    value = _int_or_none(value)
    if value is None:
        return default
    return value


def ai_llm_model_choices():
    return [
      (item["model"], item["label"])
      for item in LLM_MODEL_CATALOG
    ]


def ai_llm_model_config(model):
    model = _strip(model)
    for item in LLM_MODEL_CATALOG:
        if item["model"] == model:
            return item
    return None


def ai_llm_user_row(db, user_id):
    q = db.ai_llm_user_config.user_id == user_id
    return db(q).select(db.ai_llm_user_config.ALL, limitby=(0, 1)).first()


def ai_llm_mask_api_key(api_key, visible=5):
    api_key = _strip(api_key)
    if api_key == "":
        return ""
    if len(api_key) <= visible:
        return "*" * len(api_key)
    return ("*" * (len(api_key) - visible)) + api_key[-visible:]


def ai_llm_form_defaults(row):
    if row is None:
        return dict(
          provider=DEFAULT_PROVIDER,
          base_url=DEFAULT_OPENAI_BASE_URL,
          model=DEFAULT_MODEL,
          temperature=None,
          max_tokens=None,
          completion_token_parameter=DEFAULT_COMPLETION_TOKEN_PARAMETER,
          max_tool_iterations=DEFAULT_MAX_TOOL_ITERATIONS,
          tool_result_max_chars=DEFAULT_TOOL_RESULT_MAX_CHARS,
        )
    return dict(
      provider=row.provider or DEFAULT_PROVIDER,
      base_url=row.base_url or "",
      model=row.model or "",
      temperature=row.temperature,
      max_tokens=row.max_tokens,
      completion_token_parameter=(
        row.completion_token_parameter or DEFAULT_COMPLETION_TOKEN_PARAMETER
      ),
      max_tool_iterations=(
        row.max_tool_iterations or DEFAULT_MAX_TOOL_ITERATIONS
      ),
      tool_result_max_chars=(
        row.tool_result_max_chars or DEFAULT_TOOL_RESULT_MAX_CHARS
      ),
    )


def ai_llm_store_values(vars, current_api_key=None):
    model = _strip(getattr(vars, "model", "")) or DEFAULT_MODEL
    model_config = ai_llm_model_config(model)
    if model_config is None:
        raise RuntimeError("Unsupported AI LLM model")

    api_key = _strip(getattr(vars, "api_key", ""))
    if api_key == "":
        api_key = current_api_key
    api_key = ai_llm_encrypt_api_key(api_key)

    return dict(
      provider=model_config["provider"],
      base_url=model_config["base_url"],
      model=model,
      api_key=api_key,
      temperature=_float_or_none(getattr(vars, "temperature", None)),
      max_tokens=_int_or_none(getattr(vars, "max_tokens", None)),
      completion_token_parameter=(
        _strip(getattr(vars, "completion_token_parameter", ""))
        or DEFAULT_COMPLETION_TOKEN_PARAMETER
      ),
      max_tool_iterations=_int_or_default(
        getattr(vars, "max_tool_iterations", None),
        DEFAULT_MAX_TOOL_ITERATIONS,
      ),
      tool_result_max_chars=_int_or_default(
        getattr(vars, "tool_result_max_chars", None),
        DEFAULT_TOOL_RESULT_MAX_CHARS,
      ),
    )


def ai_llm_gateway_config(row):
    if row is None:
        return None

    model = _strip(row.model)
    model_config = ai_llm_model_config(model)
    if model_config is not None:
        provider = model_config["provider"]
        base_url = model_config["base_url"]
    else:
        provider = row.provider or DEFAULT_PROVIDER
        base_url = _strip(row.base_url)

    if not base_url or not model:
        return None

    api_key = ai_llm_decrypt_api_key(row.api_key)

    return dict(
      provider=provider,
      base_url=base_url,
      model=model,
      api_key=api_key or None,
      system_prompt=SYSTEM_PROMPT,
      temperature=row.temperature,
      max_tokens=row.max_tokens,
      completion_token_parameter=(
        row.completion_token_parameter or DEFAULT_COMPLETION_TOKEN_PARAMETER
      ),
      max_tool_iterations=(
        row.max_tool_iterations or DEFAULT_MAX_TOOL_ITERATIONS
      ),
      tool_result_max_chars=(
        row.tool_result_max_chars or DEFAULT_TOOL_RESULT_MAX_CHARS
      ),
    )
