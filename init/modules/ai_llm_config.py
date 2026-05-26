LLM_PROVIDER_CHOICES = [
    ("openai_compatible", "OpenAI-compatible"),
    ("anthropic", "Anthropic"),
    ("gemini", "Gemini"),
    ("mistral", "Mistral"),
    ("azure_openai", "Azure OpenAI"),
]
DEFAULT_PROVIDER = "openai_compatible"
DEFAULT_COMPLETION_TOKEN_PARAMETER = "max_completion_tokens"
DEFAULT_MAX_TOOL_ITERATIONS = 5
DEFAULT_TOOL_RESULT_MAX_CHARS = 20000
SYSTEM_PROMPT = (
    "You are an OpenSVC operations assistant. Answer infrastructure questions "
    "using the OpenSVC MCP tools when live collector data is needed. Discover "
    "the available tools, search for the requested object, then call the most "
    "appropriate tool with valid arguments before giving a factual answer. "
    "Never invent node, service, cluster, or compliance information. If the "
    "tool data is missing, ambiguous, or returns an error, explain that clearly "
    "and ask for the missing identifier. Do not expose secrets, API keys, "
    "tokens, or internal implementation details."
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
          base_url="",
          model="",
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
    api_key = _strip(getattr(vars, "api_key", ""))
    if api_key == "":
        api_key = current_api_key

    return dict(
      provider=_strip(getattr(vars, "provider", "")) or DEFAULT_PROVIDER,
      base_url=_strip(getattr(vars, "base_url", "")),
      model=_strip(getattr(vars, "model", "")),
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

    base_url = _strip(row.base_url)
    model = _strip(row.model)
    if not base_url or not model:
        return None

    return dict(
      provider=row.provider or DEFAULT_PROVIDER,
      base_url=base_url,
      model=model,
      api_key=row.api_key or None,
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
