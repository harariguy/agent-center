"""Remote MCP: protocol handling, the tool contract, and per-agent identity."""

import json


def rpc(client, auth, method, params=None, msg_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        body["id"] = msg_id
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=auth)


def call_tool(client, auth, name, arguments, msg_id=1):
    return rpc(client, auth, "tools/call", {"name": name, "arguments": arguments}, msg_id)


ACTIVITY = {
    "title": "Opened PROJ-42 — investigate flaky deploy",
    "group_key": "PROJ-42",
    "type": "ticket.created",
    "source_app": "linear",
    "source_link": "https://linear.app/acme/issue/PROJ-42",
}


# --- transport and auth ---------------------------------------------------------


def test_mcp_requires_a_token(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


def test_get_has_no_stream_and_delete_has_no_session(client, auth):
    assert client.get("/mcp", headers=auth).status_code == 405
    assert client.delete("/mcp", headers=auth).status_code == 405


def test_bad_json_is_a_parse_error_not_a_500(client, auth):
    r = client.post("/mcp", content=b"{nope", headers={**auth, "Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32700


def test_jsonrpc_notification_is_accepted_without_a_reply(client, auth):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=auth)
    assert r.status_code == 202
    assert not r.content


def test_batched_requests_return_an_array(client, auth):
    r = client.post("/mcp", json=[
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ], headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) == 2
    assert [m["id"] for m in body] == [1, 2]


# --- handshake ------------------------------------------------------------------


def test_initialize_echoes_a_known_protocol_and_ships_the_guide(client, auth):
    r = rpc(client, auth, "initialize", {"protocolVersion": "2025-03-26",
                                         "capabilities": {},
                                         "clientInfo": {"name": "test", "version": "0"}})
    result = r.json()["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["serverInfo"]["name"] == "agent-notify"
    # The usage contract travels with the connection.
    assert "group_key" in result["instructions"]
    assert r.headers["mcp-protocol-version"]


def test_initialize_falls_back_for_an_unknown_protocol(client, auth):
    r = rpc(client, auth, "initialize", {"protocolVersion": "1999-01-01"})
    assert r.json()["result"]["protocolVersion"] == "2025-06-18"


def test_unknown_method_is_method_not_found(client, auth):
    assert rpc(client, auth, "does/not/exist").json()["error"]["code"] == -32601


def test_unadvertised_capabilities_answer_empty(client, auth):
    assert rpc(client, auth, "prompts/list").json()["result"]["prompts"] == []
    assert rpc(client, auth, "resources/list").json()["result"]["resources"] == []


# --- the tool contract ----------------------------------------------------------


def test_tools_list_exposes_the_four_tools(client, auth):
    tools = rpc(client, auth, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "report_activity", "request_input",
        "list_open_notifications", "resolve_notification",
    }


def test_group_key_is_required_by_the_tool_even_though_the_api_allows_none(client, auth):
    tools = {t["name"]: t for t in rpc(client, auth, "tools/list").json()["result"]["tools"]}
    schema = tools["report_activity"]["inputSchema"]
    assert "group_key" in schema["required"]
    # The HTTP API deliberately does not require it — strictness lives in the facade.
    assert client.post("/api/v1/notifications",
                       json={"type": "x.y", "title": "no key here"},
                       headers=auth).status_code == 201


def test_schemas_are_flat_for_client_compatibility(client, auth):
    tools = rpc(client, auth, "tools/list").json()["result"]["tools"]
    blob = json.dumps(tools)
    assert "$ref" not in blob and "$defs" not in blob
    # Field descriptions carry the discipline rules to the call site.
    report = next(t for t in tools if t["name"] == "report_activity")
    assert "occurrence" in report["inputSchema"]["properties"]["group_key"]["description"]


# --- writing --------------------------------------------------------------------


def test_report_activity_lands_in_the_feed(client, auth):
    r = call_tool(client, auth, "report_activity", ACTIVITY)
    result = r.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["created"] is True

    items = client.get("/api/v1/notifications").json()["items"]
    assert len(items) == 1
    assert items[0]["category"] == "activity"
    assert items[0]["group_key"] == "PROJ-42"
    assert items[0]["source_app"] == "linear"


def test_request_input_is_attention(client, auth):
    call_tool(client, auth, "request_input", {
        "title": "Which entity paid the Meridian invoice?",
        "group_key": "PROJ-182",
        "type": "input.needed",
        "priority": "high",
    })
    items = client.get("/api/v1/notifications?category=attention").json()["items"]
    assert len(items) == 1
    assert items[0]["priority"] == "high"


def test_same_group_key_folds_and_reports_the_count(client, auth):
    call_tool(client, auth, "report_activity", ACTIVITY)
    second = call_tool(client, auth, "report_activity", ACTIVITY).json()["result"]
    assert second["structuredContent"]["created"] is False
    assert second["structuredContent"]["occurrences"] == 2
    assert "2 occurrences" in second["content"][0]["text"]
    assert len(client.get("/api/v1/notifications").json()["items"]) == 1


def test_idempotency_key_suppresses_a_replayed_delivery(client, auth):
    args = {**ACTIVITY, "idempotency_key": "retry-1"}
    call_tool(client, auth, "report_activity", args)
    replay = call_tool(client, auth, "report_activity", args).json()["result"]
    assert replay["structuredContent"]["deduplicated"] is True
    assert replay["structuredContent"]["occurrences"] == 1


def test_a_link_without_an_app_keeps_its_link(client, auth):
    call_tool(client, auth, "report_activity", {
        "title": "Deploy finished",
        "group_key": "deploy-prod",
        "type": "job.finished",
        "source_link": "https://github.com/acme/app/actions/runs/9",
    })
    item = client.get("/api/v1/notifications").json()["items"][0]
    assert item["source_link"].endswith("/runs/9")
    assert item["source_app"] == "github"


def test_invalid_arguments_come_back_as_a_tool_error_the_model_can_read(client, auth):
    r = call_tool(client, auth, "report_activity", {"title": "no group key", "type": "x.y"})
    body = r.json()
    # A protocol error would hide this from the model; a tool error lets it retry.
    assert "error" not in body
    assert body["result"]["isError"] is True
    assert "group_key" in body["result"]["content"][0]["text"]


def test_unknown_tool_is_a_protocol_error(client, auth):
    body = call_tool(client, auth, "nope", {}).json()
    assert body["error"]["code"] == -32602
    assert "report_activity" in body["error"]["message"]


# --- reading and resolving ------------------------------------------------------


def test_list_open_notifications_is_scoped_to_the_calling_agent(client, auth):
    call_tool(client, auth, "report_activity", ACTIVITY)
    other = client.post("/api/v1/agents", json={"name": "other"}).json()["token"]
    other_auth = {"Authorization": f"Bearer {other}"}
    call_tool(client, other_auth, "report_activity", {**ACTIVITY, "group_key": "OTHER-1"})

    mine = call_tool(client, auth, "list_open_notifications", {}).json()["result"]
    keys = [i["group_key"] for i in mine["structuredContent"]["items"]]
    assert keys == ["PROJ-42"]

    theirs = call_tool(client, other_auth, "list_open_notifications", {}).json()["result"]
    assert [i["group_key"] for i in theirs["structuredContent"]["items"]] == ["OTHER-1"]


def test_list_open_notifications_filters_to_attention(client, auth):
    call_tool(client, auth, "report_activity", ACTIVITY)
    call_tool(client, auth, "request_input",
              {"title": "Need a decision", "group_key": "ASK-1", "type": "input.needed"})
    result = call_tool(client, auth, "list_open_notifications",
                       {"only_attention": True}).json()["result"]
    assert [i["group_key"] for i in result["structuredContent"]["items"]] == ["ASK-1"]


def test_list_open_notifications_marks_its_output_as_data_not_instructions(client, auth):
    """Listed titles quote outside text (error output, ticket bodies) written in
    earlier sessions — the marker travels with the content so even an agent that
    never fetched the guide doesn't read them as directives."""
    call_tool(client, auth, "report_activity", ACTIVITY)
    result = call_tool(client, auth, "list_open_notifications", {}).json()["result"]
    assert "not instructions" in result["content"][0]["text"]


def test_resolve_notification_clears_the_agents_own_item(client, auth):
    call_tool(client, auth, "request_input",
              {"title": "Need a decision", "group_key": "ASK-1", "type": "input.needed"})
    result = call_tool(client, auth, "resolve_notification",
                       {"group_key": "ASK-1"}).json()["result"]
    assert result["structuredContent"]["resolved"] is True
    assert client.get("/api/v1/notifications").json()["items"] == []
    assert len(client.get("/api/v1/notifications?archived=true").json()["items"]) == 1


def test_resolving_something_that_is_not_open_says_so(client, auth):
    result = call_tool(client, auth, "resolve_notification",
                       {"group_key": "ghost"}).json()["result"]
    assert result["structuredContent"]["resolved"] is False
    assert result["isError"] is False


def test_resolve_cannot_reach_another_agents_notification(client, auth):
    call_tool(client, auth, "report_activity", ACTIVITY)
    other = client.post("/api/v1/agents", json={"name": "other"}).json()["token"]
    result = call_tool(client, {"Authorization": f"Bearer {other}"},
                       "resolve_notification", {"group_key": "PROJ-42"}).json()["result"]
    assert result["structuredContent"]["resolved"] is False
    assert len(client.get("/api/v1/notifications").json()["items"]) == 1


# --- the guide ------------------------------------------------------------------


def test_guide_is_served_as_markdown(client):
    r = client.get("/api/v1/guide.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "group_key" in r.text


def test_guide_matches_the_mcp_instructions(client, auth):
    served = client.get("/api/v1/guide.md").text
    instructions = rpc(client, auth, "initialize", {}).json()["result"]["instructions"]
    assert served == instructions


# --- the installable skill ------------------------------------------------------


def test_skill_is_served_with_frontmatter_an_agent_can_install(client):
    r = client.get("/api/v1/skill.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert body.startswith("---")
    for field in ("name: agent-notify", "description:", "triggers:"):
        assert field in body


def test_skill_triggers_are_post_conditions_not_user_requests(client):
    """The whole point: phrased as things the agent did, it fires unprompted.

    Phrased as "user asks to notify" — the way most skills are written — it only
    ever fires once the user already thought to ask, which is the failure it
    exists to prevent.
    """
    triggers = client.get("/api/v1/skill.md").text.split("triggers:")[1].split("---")[0]
    lines = [ln.strip(" -") for ln in triggers.strip().splitlines() if ln.strip()]
    assert lines
    assert all(ln.startswith(("you ", "a ", "the user asks what"))
               for ln in lines), lines
    # Exactly one reactive trigger is allowed: being asked for a status readout.
    assert sum(ln.startswith("the user asks") for ln in lines) <= 1


def test_skill_steers_agents_off_desktop_toasts(client):
    """A harness on macOS reads "notification" and reaches for osascript."""
    body = client.get("/api/v1/skill.md").text
    assert "osascript" in body
    assert "not the macOS Notification Center" in body


def test_skill_urls_resolve_against_the_requested_host(client):
    body = client.get("/api/v1/skill.md").text
    assert "{base}" not in body
    assert "/api/v1/guide.md" in body
    assert "http://testserver/api/v1/guide.md" in body


def test_non_web_link_is_a_readable_tool_error(client, auth):
    """A javascript: link fails as a tool error the model can read and fix,
    at the facade — not as a 500 from inside the handler."""
    result = call_tool(client, auth, "report_activity", {
        "type": "job.done", "title": "hi", "group_key": "PROJ-1",
        "source_link": "javascript:alert(1)",
    }).json()["result"]
    assert result["isError"] is True
    assert "http" in result["content"][0]["text"]

    result = call_tool(client, auth, "report_activity", {
        "type": "job.done", "title": "hi", "group_key": "PROJ-1",
        "actions": [{"label": "Open", "url": "data:text/html,hi"}],
    }).json()["result"]
    assert result["isError"] is True
