# HOLON-META: {
#   purpose: "ofshore-mcp",
#   morphic_field: "agent-state:4c67a2b1-6830-44ec-97b1-7c8f93722add",
#   startup_protocol: "READ morphic_field + biofield_external + em_grid",
#   wiki: "32d6d069-74d6-8164-a6d5-f41c3d26ae9b"
# }

#!/usr/bin/env python3
"""
ofshore-ecosystem MCP Server
Gives Claude direct tools to control and monitor the entire ofshore.dev ecosystem.

Tools:
- execute_sql         — run SQL on Supabase
- deploy_app          — trigger Coolify deployment
- app_status          — get status of all Coolify apps
- send_telegram       — send message via Guardian bot
- brain_router_chat   — query brain-router AI
- cognitive_mind_push — publish knowledge to CognitiveMind
- cognitive_mind_groq — run Groq query via CM DO
- n8n_trigger         — trigger n8n webhook
- upstash_get/set     — read/write Upstash Redis
- github_file_get     — read file from GitHub
- github_file_put     — write file to GitHub
- ecosystem_audit     — full parallel health check
- worker_call         — call any CF Worker endpoint
"""

import asyncio
import json
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
)

# ── Config ────────────────────────────────────────────────────────────────────
SUPA_URL   = "https://blgdhfcosqjzrutncbbr.supabase.co"
SUPA_SVC   = os.getenv("SUPABASE_SERVICE_KEY", "SET_VIA_ENV")
COOLIFY    = "https://coolify.ofshore.dev"
COOLIFY_T  = os.getenv("COOLIFY_TOKEN", "SET_VIA_ENV")
TG_BOT     = os.getenv("TG_BOT", "SET_VIA_ENV")
TG_CHAT    = os.getenv("TG_CHAT", "SET_VIA_ENV")
BRAIN      = "https://brain-router.maciej-koziej01.workers.dev"
BRAIN_KEY  = os.getenv("BRAIN_KEY", "SET_VIA_ENV")
CM_URL     = "https://cognitive-mind.maciej-koziej01.workers.dev"
N8N_BRIDGE = "https://n8n-bridge.maciej-koziej01.workers.dev"
UPSTASH    = "https://fresh-walleye-84119.upstash.io"
UPSTASH_T  = os.getenv("UPSTASH_TOKEN", "SET_VIA_ENV")
GITHUB_T   = os.getenv("GITHUB_TOKEN", "SET_VIA_ENV")

sh = {"apikey": SUPA_SVC, "Authorization": f"Bearer {SUPA_SVC}", "Content-Type": "application/json"}
ch = {"Authorization": f"Bearer {COOLIFY_T}"}
uh = {"Authorization": f"Bearer {UPSTASH_T}"}
gh = {"Authorization": f"token {GITHUB_T}", "Accept": "application/vnd.github.v3+json"}

server = Server("ofshore-ecosystem")
client = httpx.AsyncClient(timeout=20.0)

# ── Tools definition ──────────────────────────────────────────────────────────
TOOLS = [
    Tool(name="execute_sql", description="Execute SQL on Supabase blgdhfcosqjzrutncbbr. Returns rows as JSON.",
         inputSchema={"type":"object","properties":{"sql":{"type":"string","description":"SQL query to execute"}},"required":["sql"]}),

    Tool(name="deploy_app", description="Trigger Coolify deployment for an application by UUID or name.",
         inputSchema={"type":"object","properties":{
             "uuid":{"type":"string","description":"Coolify app UUID"},
             "name":{"type":"string","description":"App name (alternative to UUID)"},
             "force":{"type":"boolean","default":True}},"required":[]}),

    Tool(name="app_status", description="Get status of all Coolify applications and services.",
         inputSchema={"type":"object","properties":{},"required":[]}),

    Tool(name="send_telegram", description="Send a message via Telegram Guardian bot to Maciej.",
         inputSchema={"type":"object","properties":{
             "message":{"type":"string","description":"Message text"},
             "parse_mode":{"type":"string","default":"","enum":["","Markdown","HTML"]}},"required":["message"]}),

    Tool(name="brain_router_chat", description="Send a prompt to brain-router AI (Groq llama, $0 cost).",
         inputSchema={"type":"object","properties":{
             "prompt":{"type":"string"},
             "path":{"type":"string","default":"reflex","enum":["reflex","think","reason","code"]}},"required":["prompt"]}),

    Tool(name="cognitive_mind_push", description="Publish knowledge to CognitiveMind Durable Object (broadcasts to all WS nodes).",
         inputSchema={"type":"object","properties":{
             "topic":{"type":"string"},
             "event":{"type":"string","default":"learn"},
             "payload":{"type":"object"}},"required":["topic","payload"]}),

    Tool(name="cognitive_mind_groq", description="Run Groq inference via CognitiveMind edge DO (cached, fast).",
         inputSchema={"type":"object","properties":{
             "prompt":{"type":"string"},
             "max_tokens":{"type":"integer","default":500}},"required":["prompt"]}),

    Tool(name="cognitive_mind_state", description="Get current state for a topic from CognitiveMind KV cache.",
         inputSchema={"type":"object","properties":{"key":{"type":"string"}},"required":["key"]}),

    Tool(name="n8n_trigger", description="Trigger an n8n webhook via n8n-bridge CF Worker.",
         inputSchema={"type":"object","properties":{
             "webhook":{"type":"string","description":"Webhook name",
                        "enum":["autoheal-alert","agent-factory","automation","agent-task",
                                "deploy-notification","health-alert","cost-alert","integration-agent",
                                "wp-security","site-audit","bot-army","scan-competitor"]},
             "payload":{"type":"object"}},"required":["webhook"]}),

    Tool(name="upstash_get", description="Get value from Upstash Redis.",
         inputSchema={"type":"object","properties":{"key":{"type":"string"}},"required":["key"]}),

    Tool(name="upstash_set", description="Set value in Upstash Redis with optional TTL.",
         inputSchema={"type":"object","properties":{
             "key":{"type":"string"},"value":{"type":"string"},
             "ttl_seconds":{"type":"integer","default":3600}},"required":["key","value"]}),

    Tool(name="github_file_get", description="Read a file from a GitHub repository.",
         inputSchema={"type":"object","properties":{
             "repo":{"type":"string","description":"e.g. szachmacik/brain-router"},
             "path":{"type":"string","description":"file path in repo"}},"required":["repo","path"]}),

    Tool(name="github_file_put", description="Write/update a file in a GitHub repository.",
         inputSchema={"type":"object","properties":{
             "repo":{"type":"string"},"path":{"type":"string"},
             "content":{"type":"string"},"message":{"type":"string"}},"required":["repo","path","content","message"]}),

    Tool(name="ecosystem_audit", description="Run full parallel health check on all ecosystem components. Returns score and issues.",
         inputSchema={"type":"object","properties":{},"required":[]}),

    Tool(name="worker_call", description="Call any Cloudflare Worker endpoint.",
         inputSchema={"type":"object","properties":{
             "worker":{"type":"string","description":"Worker name, e.g. brain-router"},
             "path":{"type":"string","default":"/health"},
             "method":{"type":"string","default":"GET","enum":["GET","POST"]},
             "body":{"type":"object"}},"required":["worker"]}),

    Tool(name="coolify_restart", description="Restart a Coolify application.",
         inputSchema={"type":"object","properties":{
             "uuid":{"type":"string","description":"Coolify app UUID"}},"required":["uuid"]}),
]

# ── Tool handlers ─────────────────────────────────────────────────────────────
async def handle_execute_sql(args):
    r = await client.post(f"{SUPA_URL}/rest/v1/rpc/execute_sql_with_result",
        headers=sh, json={"query": args["sql"]})
    if r.status_code == 200:
        return r.text[:3000]
    # Fallback to direct query for SELECTs
    return f"Error {r.status_code}: {r.text[:200]}"

async def handle_deploy_app(args):
    uuid = args.get("uuid")
    if not uuid and args.get("name"):
        r = await client.get(f"{COOLIFY}/api/v1/applications", headers=ch)
        apps = r.json()
        for a in apps:
            if args["name"].lower() in a.get("name","").lower():
                uuid = a["uuid"]; break
    if not uuid:
        return "Error: app not found. Provide uuid or valid name."
    force = args.get("force", True)
    r = await client.post(f"{COOLIFY}/api/v1/deploy?uuid={uuid}&force={'true' if force else 'false'}", headers=ch)
    d = r.json()
    dep = d.get("deployments",[{}])[0]
    return json.dumps({"queued": True, "deploy_uuid": dep.get("deployment_uuid","?"), "app": uuid})

async def handle_app_status(args):
    apps_r = await client.get(f"{COOLIFY}/api/v1/applications", headers=ch)
    svcs_r = await client.get(f"{COOLIFY}/api/v1/services", headers=ch)
    apps = apps_r.json() if apps_r.status_code == 200 else []
    svcs = svcs_r.json() if svcs_r.status_code == 200 else []
    
    result = {"apps": {}, "services": {}, "summary": {}}
    healthy = dead = unknown = 0
    
    for a in apps:
        s = a.get("status","?")
        n = a.get("name","?")
        if "healthy" in s: healthy += 1
        elif "exited" in s or "unhealthy" in s: dead += 1
        else: unknown += 1
        result["apps"][n] = s
    
    for s in (svcs if isinstance(svcs, list) else []):
        result["services"][s.get("name","?")] = s.get("status","?")
    
    result["summary"] = {"healthy": healthy, "dead": dead, "unknown": unknown, "total": len(apps)}
    return json.dumps(result, indent=2)

async def handle_send_telegram(args):
    msg = args["message"]
    parse_mode = args.get("parse_mode","")
    payload = {"chat_id": TG_CHAT, "text": msg}
    if parse_mode: payload["parse_mode"] = parse_mode
    r = await client.post(f"https://api.telegram.org/bot{TG_BOT}/sendMessage", json=payload)
    d = r.json()
    return f"Sent: {d.get('ok')} | message_id: {d.get('result',{}).get('message_id','?')}"

async def handle_brain_router_chat(args):
    r = await client.post(f"{BRAIN}/chat",
        headers={"Content-Type":"application/json","x-app-token":BRAIN_KEY,"x-urgency":"realtime"},
        json={"prompt": args["prompt"], "force_path": args.get("path","reflex")})
    d = r.json()
    return json.dumps({"text": d.get("text",""), "model": d.get("model",""), 
                       "latency_ms": d.get("latency_ms"), "cost": d.get("cost_usd",0)})

async def handle_cm_push(args):
    r = await client.post(f"{CM_URL}/push", json={
        "type":"publish", "topic": args["topic"], "event": args.get("event","learn"),
        "payload": args["payload"], "source_node": "claude-mcp"
    })
    return r.text[:200]

async def handle_cm_groq(args):
    r = await client.post(f"{CM_URL}/groq", json={"prompt": args["prompt"], "max_tokens": args.get("max_tokens",500)})
    d = r.json()
    return json.dumps({"text": d.get("text",""), "cached": d.get("cached"), "latency_ms": d.get("latency_ms")})

async def handle_cm_state(args):
    r = await client.get(f"{CM_URL}/state/{args['key']}")
    return r.text[:500]

async def handle_n8n_trigger(args):
    r = await client.post(f"{N8N_BRIDGE}/trigger/{args['webhook']}",
        headers={"Content-Type":"application/json"}, json=args.get("payload",{}))
    return r.text[:300]

async def handle_upstash_get(args):
    r = await client.get(f"{UPSTASH}/get/{args['key']}", headers=uh)
    return r.text[:500]

async def handle_upstash_set(args):
    ttl = args.get("ttl_seconds", 3600)
    r = await client.get(f"{UPSTASH}/set/{args['key']}/{args['value']}/EX/{ttl}", headers=uh)
    return r.text[:100]

async def handle_github_get(args):
    import base64
    r = await client.get(f"https://api.github.com/repos/{args['repo']}/contents/{args['path']}", headers=gh)
    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode()
        return content[:5000]
    return f"Error {r.status_code}: {r.text[:200]}"

async def handle_github_put(args):
    import base64
    # Get SHA
    r = await client.get(f"https://api.github.com/repos/{args['repo']}/contents/{args['path']}", headers=gh)
    sha = r.json().get("sha","") if r.status_code == 200 else ""
    payload = {"message": args["message"], "content": base64.b64encode(args["content"].encode()).decode()}
    if sha: payload["sha"] = sha
    r2 = await client.put(f"https://api.github.com/repos/{args['repo']}/contents/{args['path']}",
        headers=gh, json=payload)
    d = r2.json()
    return f"commit: {d.get('commit',{}).get('sha','err')[:12]} | status: {r2.status_code}"

async def handle_ecosystem_audit(args):
    workers = [
        "brain-router","cognitive-mind","agent-router","n8n-bridge",
        "task-executor","watchdog-v2","coolify-agent","ecosystem-coordinator",
    ]
    async def check_w(name):
        try:
            r = await client.get(f"https://{name}.maciej-koziej01.workers.dev/health", timeout=6)
            return name, r.status_code, "ok" if r.status_code==200 else r.text[:40]
        except Exception as e:
            return name, 0, str(e)[:40]
    
    tasks = [check_w(w) for w in workers]
    results = await asyncio.gather(*tasks)
    ok = sum(1 for _,c,_ in results if c==200)
    return json.dumps({
        "score": f"{ok}/{len(workers)}",
        "workers": {n: {"code":c,"info":i} for n,c,i in results},
        "integration_hub": (await client.get("https://hub.ofshore.dev/api/health", timeout=5)).status_code,
    }, indent=2)

async def handle_worker_call(args):
    worker = args["worker"]
    path = args.get("path", "/health")
    method = args.get("method","GET")
    url = f"https://{worker}.maciej-koziej01.workers.dev{path}"
    if method == "GET":
        r = await client.get(url, timeout=10)
    else:
        r = await client.post(url, json=args.get("body",{}), timeout=10)
    return r.text[:2000]

async def handle_coolify_restart(args):
    r = await client.post(f"{COOLIFY}/api/v1/applications/{args['uuid']}/restart", headers=ch)
    return f"restart: {r.status_code} {r.text[:100]}"

# ── MCP handlers ──────────────────────────────────────────────────────────────
@server.list_tools()
async def list_tools(req: ListToolsRequest) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)

@server.call_tool()
async def call_tool(req: CallToolRequest) -> CallToolResult:
    name = req.params.name
    args = req.params.arguments or {}
    
    try:
        dispatch = {
            "execute_sql": handle_execute_sql,
            "deploy_app": handle_deploy_app,
            "app_status": handle_app_status,
            "send_telegram": handle_send_telegram,
            "brain_router_chat": handle_brain_router_chat,
            "cognitive_mind_push": handle_cm_push,
            "cognitive_mind_groq": handle_cm_groq,
            "cognitive_mind_state": handle_cm_state,
            "n8n_trigger": handle_n8n_trigger,
            "upstash_get": handle_upstash_get,
            "upstash_set": handle_upstash_set,
            "github_file_get": handle_github_get,
            "github_file_put": handle_github_put,
            "ecosystem_audit": handle_ecosystem_audit,
            "worker_call": handle_worker_call,
            "coolify_restart": handle_coolify_restart,
        }
        
        handler = dispatch.get(name)
        if not handler:
            return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
        
        result = await handler(args)
        return CallToolResult(content=[TextContent(type="text", text=str(result))])
    
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {e}")], isError=True)

# ── Entry ─────────────────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
