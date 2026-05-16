class rest_get_ai_llm_config(rest_get_handler):
    def __init__(self):
        desc = [
          "Return the AI LLM configuration used by the OpenSVC AI gateway.",
        ]
        examples = [
          """# curl -u %(email)s -H "X-OpenSVC-Gateway-Token: <token>" -o- https://%(collector)s/init/rest/api/ai/llm/config""",
        ]
        rest_get_handler.__init__(
          self,
          path="/ai/llm/config",
          desc=desc,
          examples=examples,
        )

    def handler(self, **vars):
        _require_ai_gateway_token()

        base_url = config_get("ai_llm_base_url", "")
        model = config_get("ai_llm_model", "")
        if not base_url or not model:
            raise HTTP(
              503,
              "AI LLM config is incomplete: ai_llm_base_url and ai_llm_model are required",
            )

        return dict(data={
          "provider": config_get("ai_llm_provider", "openai_compatible"),
          "base_url": base_url,
          "model": model,
          "api_key": config_get("ai_llm_api_key", None) or None,
          "system_prompt": config_get("ai_llm_system_prompt", ""),
          "temperature": config_get("ai_llm_temperature", None),
          "max_tokens": config_get("ai_llm_max_tokens", None),
          "completion_token_parameter": config_get(
            "ai_llm_completion_token_parameter",
            "max_completion_tokens",
          ),
          "max_tool_iterations": config_get("ai_llm_max_tool_iterations", 5),
          "tool_result_max_chars": config_get("ai_llm_tool_result_max_chars", 20000),
        })


def _require_ai_gateway_token():
    expected = config_get("ai_gateway_internal_token", None)
    if not expected:
        raise HTTP(503, "AI gateway internal token is not configured")

    received = getattr(request.env, "http_x_opensvc_gateway_token", None)
    if received != expected:
        raise HTTP(403, "Invalid AI gateway internal token")
