from applications.init.modules.ai_llm_config import (
    ai_llm_gateway_config,
    ai_llm_user_row,
)


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

        try:
            data = ai_llm_gateway_config(db, ai_llm_user_row(db, auth.user_id))
        except RuntimeError as exc:
            raise HTTP(503, str(exc))
        if data is None:
            raise HTTP(
              503,
              "AI LLM config is not configured for this user",
            )

        return dict(data=data)


def _require_ai_gateway_token():
    expected = config_get("ai_gateway_internal_token", None)
    if not expected:
        raise HTTP(503, "AI gateway internal token is not configured")

    received = getattr(request.env, "http_x_opensvc_gateway_token", None)
    if received != expected:
        raise HTTP(403, "Invalid AI gateway internal token")
