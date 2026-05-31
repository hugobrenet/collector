import gluon.contrib.simplejson as json

from applications.init.modules.ai_gateway import AiGatewayError, ai_gateway_chat
from applications.init.modules.ai_llm_config import (
    DEFAULT_COMPLETION_TOKEN_PARAMETER,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_TOOL_RESULT_MAX_CHARS,
    LLM_PROVIDER_CHOICES,
    LLM_SELECTABLE_PROVIDER_VALUES,
    ai_llm_form_defaults,
    ai_llm_mask_api_key,
    ai_llm_store_values,
    ai_llm_user_row,
)

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)

AI_CHAT_HISTORY_LIMIT = 20


def _json_response(data):
    response.headers["Content-Type"] = "application/json"
    return json.dumps(data)


def _json_payload(allow_empty=False):
    body = request.body.read()
    if not body and allow_empty:
        return {}

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTP(400, json.dumps({"error": "Invalid JSON payload"}))

    if not isinstance(payload, dict):
        raise HTTP(400, json.dumps({"error": "JSON payload must be an object"}))
    return payload


def _method():
    return request.env.request_method.upper()


def _conversation_or_404(conversation_id):
    try:
        conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        raise HTTP(404, json.dumps({"error": "Conversation not found"}))

    row = db(
      (db.ai_chat_conversation.id == conversation_id) &
      (db.ai_chat_conversation.user_id == auth.user_id) &
      (db.ai_chat_conversation.deleted == False)
    ).select().first()

    if row is None:
        raise HTTP(404, json.dumps({"error": "Conversation not found"}))
    return row


def _conversation_dict(row):
    return {
      "id": row.id,
      "title": row.title,
      "created": _datetime_value(row.created),
      "updated": _datetime_value(row.updated),
    }


def _message_dict(row):
    return {
      "id": row.id,
      "conversation_id": row.conversation_id,
      "role": row.role,
      "content": row.content,
      "tool_calls": _json_field(row.tool_calls),
      "metadata": _json_field(row.metadata),
      "created": _datetime_value(row.created),
    }


def _datetime_value(value):
    if value is None:
        return None
    return value.isoformat(" ")


def _json_field(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


def _clean_title(value):
    if not isinstance(value, string_types):
        return "New conversation"

    value = value.strip()
    if not value:
        return "New conversation"
    return value[:255]


def _validated_message(payload):
    message = payload.get("message")
    if not isinstance(message, string_types) or not message.strip():
        raise HTTP(400, json.dumps({"error": "Missing or empty message"}))
    return message.strip()


def _history_messages(conversation_id):
    rows = db(
      (db.ai_chat_message.conversation_id == conversation_id) &
      (db.ai_chat_message.user_id == auth.user_id) &
      (db.ai_chat_message.role.belongs(("user", "assistant")))
    ).select(
      orderby=~db.ai_chat_message.created,
      limitby=(0, AI_CHAT_HISTORY_LIMIT),
    )
    rows = list(rows)
    rows.reverse()
    return [
      {"role": row.role, "content": row.content}
      for row in rows
      if row.content
    ]


def _json_dump_field(value):
    if value is None:
        return None
    return json.dumps(value)


def _provider_select_widget(field, value, provider_options):
    active_values = [item[0] for item in provider_options if item[2]]
    if value not in active_values:
        value = active_values[0]

    field_id = "%s_%s" % (getattr(field, "_tablename", "no_table"), field.name)
    options = []
    for provider, label, enabled in provider_options:
        attrs = {"_value": provider}
        if provider == value:
            attrs["_selected"] = "selected"
        if not enabled:
            attrs["_disabled"] = "disabled"
            attrs["_title"] = T("Provider adapter not enabled yet")
        options.append(OPTION(label, **attrs))
    return SELECT(*options, _name=field.name, _id=field_id)


@auth.requires_login()
def chatbot():
    return dict()


@auth.requires_login()
def conversations():
    if len(request.args) == 0 and _method() == "GET":
        rows = db(
          (db.ai_chat_conversation.user_id == auth.user_id) &
          (db.ai_chat_conversation.deleted == False)
        ).select(orderby=~db.ai_chat_conversation.updated)
        return _json_response({
          "conversations": [_conversation_dict(row) for row in rows],
        })

    if len(request.args) == 0 and _method() == "POST":
        payload = _json_payload(allow_empty=True)
        now = request.now
        conversation_id = db.ai_chat_conversation.insert(
          user_id=auth.user_id,
          title=_clean_title(payload.get("title")),
          created=now,
          updated=now,
          deleted=False,
        )
        row = db.ai_chat_conversation[conversation_id]
        return _json_response({"conversation": _conversation_dict(row)})

    if len(request.args) == 1 and _method() == "DELETE":
        row = _conversation_or_404(request.args[0])
        row.update_record(deleted=True, updated=request.now)
        return _json_response({"deleted": True, "id": row.id})

    if (
      len(request.args) == 2 and
      request.args[1] == "chat" and
      _method() == "POST"
    ):
        row = _conversation_or_404(request.args[0])
        payload = _json_payload()
        message = _validated_message(payload)
        gateway_payload = dict(payload)
        gateway_payload["message"] = message
        gateway_payload["history"] = _history_messages(row.id)

        try:
            gateway_response = ai_gateway_chat(
              session,
              config_get,
              gateway_payload,
            )
        except AiGatewayError as exc:
            raise HTTP(exc.status_code, json.dumps({"error": exc.detail}))

        if not isinstance(gateway_response, dict):
            raise HTTP(502, json.dumps({"error": "Invalid AI gateway response"}))

        now = request.now
        user_message_id = db.ai_chat_message.insert(
          conversation_id=row.id,
          user_id=auth.user_id,
          role="user",
          content=message,
          created=now,
        )
        assistant_message_id = db.ai_chat_message.insert(
          conversation_id=row.id,
          user_id=auth.user_id,
          role="assistant",
          content=gateway_response.get("message") or "",
          tool_calls=_json_dump_field(gateway_response.get("tool_calls")),
          metadata=_json_dump_field({
            "provider": gateway_response.get("provider"),
            "model": gateway_response.get("model"),
          }),
          created=now,
        )
        row.update_record(updated=now)

        gateway_response["conversation_id"] = row.id
        gateway_response["user_message_id"] = user_message_id
        gateway_response["assistant_message_id"] = assistant_message_id
        return _json_response(gateway_response)

    if (
      len(request.args) == 2 and
      request.args[1] == "messages" and
      _method() == "GET"
    ):
        row = _conversation_or_404(request.args[0])
        messages = db(
          (db.ai_chat_message.conversation_id == row.id) &
          (db.ai_chat_message.user_id == auth.user_id)
        ).select(orderby=db.ai_chat_message.created)
        return _json_response({
          "conversation": _conversation_dict(row),
          "messages": [_message_dict(message) for message in messages],
        })

    raise HTTP(404, json.dumps({"error": "Endpoint not found"}))


@auth.requires_login()
def config():
    row = ai_llm_user_row(db, auth.user_id)
    defaults = ai_llm_form_defaults(row)
    masked_api_key = ai_llm_mask_api_key(row.api_key if row is not None else None)
    provider_options = [
      (
        item[0],
        T(item[1]),
        item[0] in LLM_SELECTABLE_PROVIDER_VALUES,
      )
      for item in LLM_PROVIDER_CHOICES
    ]
    provider_values = [item[0] for item in provider_options if item[2]]
    provider_labels = [item[1] for item in provider_options if item[2]]

    form = SQLFORM.factory(
      Field(
        "provider",
        "string",
        default=defaults["provider"],
        label=T("Provider"),
        requires=IS_IN_SET(provider_values, labels=provider_labels, zero=None),
        widget=lambda field, value: _provider_select_widget(
          field,
          value,
          provider_options,
        ),
      ),
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
