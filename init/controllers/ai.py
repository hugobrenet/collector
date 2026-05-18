import gluon.contrib.simplejson as json

from applications.init.modules.ai_gateway import AiGatewayError, ai_gateway_chat
from applications.init.modules.ai_llm_config import (
    DEFAULT_COMPLETION_TOKEN_PARAMETER,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_PROVIDER,
    DEFAULT_TOOL_RESULT_MAX_CHARS,
    ai_llm_form_defaults,
    ai_llm_mask_api_key,
    ai_llm_store_values,
    ai_llm_user_row,
)

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


@auth.requires_login()
def chatbot():
    return dict()


@auth.requires_login()
def chat():
    response.headers["Content-Type"] = "application/json"

    try:
        payload = json.loads(request.body.read())
    except Exception:
        raise HTTP(400, json.dumps({"error": "Invalid JSON payload"}))

    if not isinstance(payload, dict):
        raise HTTP(400, json.dumps({"error": "JSON payload must be an object"}))

    message = payload.get("message")
    if not isinstance(message, string_types) or not message.strip():
        raise HTTP(400, json.dumps({"error": "Missing or empty message"}))

    try:
        return json.dumps(ai_gateway_chat(session, config_get, payload))
    except AiGatewayError as exc:
        raise HTTP(exc.status_code, json.dumps({"error": exc.detail}))


@auth.requires_login()
def config():
    row = ai_llm_user_row(db, auth.user_id)
    defaults = ai_llm_form_defaults(row)
    masked_api_key = ai_llm_mask_api_key(row.api_key if row is not None else None)

    form = SQLFORM.factory(
      Field(
        "base_url",
        "string",
        length=512,
        default=defaults["base_url"],
        label=T("API base URL"),
        requires=IS_NOT_EMPTY(),
      ),
      Field(
        "model",
        "string",
        length=128,
        default=defaults["model"],
        label=T("Model"),
        requires=IS_NOT_EMPTY(),
      ),
      Field(
        "api_key",
        "string",
        default=masked_api_key,
        label=T("API key"),
        requires=IS_EMPTY_OR(IS_LENGTH(4096)),
      ),
      submit_button=T("Save"),
    )

    if form.process().accepted:
        current_api_key = row.api_key if row is not None else None
        if form.vars.api_key == masked_api_key:
            form.vars.api_key = ""
        form.vars.provider = DEFAULT_PROVIDER
        form.vars.temperature = None
        form.vars.max_tokens = None
        form.vars.completion_token_parameter = (
          DEFAULT_COMPLETION_TOKEN_PARAMETER
        )
        form.vars.max_tool_iterations = DEFAULT_MAX_TOOL_ITERATIONS
        form.vars.tool_result_max_chars = DEFAULT_TOOL_RESULT_MAX_CHARS
        values = ai_llm_store_values(
          form.vars,
          current_api_key=current_api_key,
        )
        values["user_id"] = auth.user_id
        values["updated"] = request.now
        db.ai_llm_user_config.update_or_insert(
          {"user_id": auth.user_id},
          **values
        )
        session.flash = T("Saved")
        redirect(URL("ai", "config"))

    return dict(
      form=form,
      api_key_configured=bool(row is not None and row.api_key),
    )
