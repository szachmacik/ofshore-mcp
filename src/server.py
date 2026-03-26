"""
ofshore-mcp — MCP Server for ofshore.dev ecosystem
Gives Claude Desktop / Cursor / any MCP client full access to:
  - System dashboard & health
  - Research insights & build queue
  - Groq inference (free, fast)
  - Upstash knowledge bus
  - Telegram messaging
  - Supabase SQL execution
  - CF Workers management
"""

import asyncio
import json
import os
import httpx
from datetime import datetime
from typing import Any
from mcp.server.fastmcp import FastMCP

# ── Config ─────────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]
GROQ_KEY      = os.environ.get("GROQ_API_KEY", "")
UPSTASH_URL   = os.environ.get("UPSTASH_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_TOKEN", "")
TG_TOKEN      = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT       = os.environ.get("TELEGRAM_CHAT_ID", "8149345223")
CF_TOKEN      = os.environ.get("CF_API_TOKEN", "")
CF_ACCOUNT    = os.environ.get("CF_ACCOUNT_ID", "9a877cdba770217082a2f914427df505")

mcp = FastMCP("ofshore-mcp", description="Direct access to ofshore.dev autonomous ecosystem")

# ── HTTP helpers ───────────────────────────────────────────────────────────────

async def supa_rpc(func: str, params: dict = {}) -> Any:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{func}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json=params,
        )
        return r.json()

async def supa_query(sql: str) -> Any:
    return await supa_rpc("execute_sql_with_result", {"sql_query": sql})

async def upstash(*cmd) -> Any:
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.post(UPSTASH_URL,
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}", "Content-Type": "application/json"},
            json=list(cmd))
        return r.json().get("result")

async def groq(prompt: str, max_tokens: int = 1000, system: str = "Jesteś agentem Holonu (ofshore.dev). Odpowiadaj precyzyjnie.") -> str:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            })
        return r.json()["choices"][0]["message"]["content"]

# ── TOOLS ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def system_dashboard() -> str:
    """Get complete real-time system dashboard: crons, AI pipeline, integrations, yeshua health."""
    result = await supa_rpc("system_dashboard")
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


@mcp.tool()
async def get_research_insights(
    status: str = "all",
    limit: int = 20,
    recommendation: str = "all"
) -> str:
    """Get research insights from AI researchers.
    
    Args:
        status: Filter by status (new/queued/all)
        limit: Max results (default 20)
        recommendation: Filter by monetization check (build_now/validate_first/all)
    """
    where_clauses = []
    if status != "all":
        where_clauses.append(f"ri.status='{status}'")
    if recommendation != "all":
        where_clauses.append(f"mc.recommendation='{recommendation}'")
    
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
    SELECT ri.researcher, ri.solution_name, ri.problem_statement,
           ri.pain_intensity, ri.estimated_monthly_eur,
           ri.solution_type, ri.solution_complexity,
           mc.recommendation, mc.score, ri.status, ri.created_at
    FROM public.research_insights ri
    LEFT JOIN public.monetization_checks mc ON mc.insight_id=ri.id
    {where}
    ORDER BY COALESCE(mc.score,0) DESC, ri.created_at DESC
    LIMIT {limit}
    """
    result = await supa_query(sql)
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


@mcp.tool()
async def get_build_queue(status: str = "queued", limit: int = 30) -> str:
    """Get items in the autonomous build queue.
    
    Args:
        status: queued/in_progress/done/all
        limit: Max results
    """
    where = "" if status == "all" else f"WHERE status='{status}'"
    sql = f"""
    SELECT id, build_type, title, description, auto_priority,
           assigned_being, status, queued_at, started_at
    FROM public.autonomous_build_queue
    {where}
    ORDER BY auto_priority DESC, queued_at ASC
    LIMIT {limit}
    """
    return json.dumps(await supa_query(sql), indent=2, ensure_ascii=False, default=str)


@mcp.tool()
async def queue_build(
    title: str,
    description: str,
    build_type: str = "feature",
    priority: float = 0.7,
    agent: str = "Solomon.Arch"
) -> str:
    """Add an item to the autonomous build queue.
    
    Args:
        title: What to build
        description: Detailed description / requirements
        build_type: feature/tool/integration/infrastructure/saas
        priority: 0.0-1.0 (1.0 = highest)
        agent: Which agent handles it
    """
    sql = f"""
    INSERT INTO public.autonomous_build_queue
      (build_type, title, description, auto_priority, assigned_being)
    VALUES
      ('{build_type}', $title$, $desc$, {priority}, '{agent}')
    RETURNING id, title, queued_at
    """
    # Use parameterized via RPC
    result = await supa_rpc("execute_sql_with_result", {
        "sql_query": f"""
        INSERT INTO public.autonomous_build_queue
          (build_type, title, description, auto_priority, assigned_being)
        VALUES
          ('{build_type}', '{title.replace("'","''")}', 
           '{description.replace("'","''")}',
           {priority}, '{agent}')
        RETURNING id::text, title, queued_at::text
        """
    })
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def run_researcher(agent_name: str = "all") -> str:
    """Trigger AI researcher(s) to find new market opportunities.
    
    Args:
        agent_name: Dr.Signal / Scout.Build / Trends.Watch / Pain.Mapper / all
    """
    if agent_name == "all":
        names = ["Dr.Signal", "Scout.Build", "Trends.Watch", "Pain.Mapper"]
    else:
        names = [agent_name]
    
    results = {}
    for name in names:
        r = await supa_rpc("run_researcher_async", {"p_agent_name": name})
        results[name] = r
    
    return json.dumps({"triggered": names, "req_ids": results,
                       "note": "Responses collected in ~10s via collect_ai_responses()"}, indent=2)


@mcp.tool()
async def collect_insights() -> str:
    """Collect pending AI responses and save new insights. Run after run_researcher()."""
    result = await supa_rpc("collect_ai_responses")
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def groq_ask(prompt: str, max_tokens: int = 1000) -> str:
    """Run a query through Groq Llama-3.3-70b (FREE, ~150ms).
    
    Args:
        prompt: Your question or task
        max_tokens: Max response length
    """
    return await groq(prompt, max_tokens)


@mcp.tool()
async def kb_write(key: str, value: Any, ttl_seconds: int = 3600) -> str:
    """Write to Upstash knowledge bus (shared state across all agents).
    
    Args:
        key: Key name (e.g. 'project.status', 'kamila.schedule')
        value: Any JSON-serializable value
        ttl_seconds: How long to cache (default 1h)
    """
    serialized = json.dumps(value) if not isinstance(value, str) else value
    result = await upstash("SET", f"kb:{key}", serialized, "EX", str(ttl_seconds))
    await upstash("LPUSH", "ch:mind_events",
                  json.dumps({"e": "kb_write", "k": key, "ts": int(datetime.now().timestamp() * 1000)}))
    return json.dumps({"stored": key, "ttl": ttl_seconds, "result": result})


@mcp.tool()
async def kb_read(key: str) -> str:
    """Read from Upstash knowledge bus.
    
    Args:
        key: Key name to read
    """
    raw = await upstash("GET", f"kb:{key}")
    if raw is None:
        return json.dumps({"key": key, "value": None, "exists": False})
    try:
        return json.dumps({"key": key, "value": json.loads(raw), "exists": True}, indent=2)
    except:
        return json.dumps({"key": key, "value": raw, "exists": True})


@mcp.tool()
async def kb_list(pattern: str = "*") -> str:
    """List keys in knowledge bus matching a pattern.
    
    Args:
        pattern: Redis pattern (e.g. 'kb:project.*', '*')
    """
    keys = await upstash("KEYS", f"kb:{pattern}")
    return json.dumps({"keys": keys or [], "count": len(keys or [])}, indent=2)


@mcp.tool()
async def send_telegram(message: str, parse_mode: str = "HTML") -> str:
    """Send a message to Maciej via Telegram Guardian bot.
    
    Args:
        message: Message text (HTML formatting supported)
        parse_mode: HTML or Markdown
    """
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": message, "parse_mode": parse_mode},
        )
        d = r.json()
    return json.dumps({"ok": d.get("ok"), "message_id": d.get("result", {}).get("message_id")})


@mcp.tool()
async def execute_sql(query: str) -> str:
    """Execute SQL query on Supabase and return results.
    
    Args:
        query: SQL query to execute (SELECT, INSERT, UPDATE, etc.)
    """
    result = await supa_query(query)
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


@mcp.tool()
async def integration_health() -> str:
    """Check real-time health of all integrations: Groq, Claude, Upstash, Telegram, brain-router."""
    # Run fresh check
    await supa_rpc("check_all_integrations")
    await asyncio.sleep(8)  # Wait for async checks
    await supa_rpc("collect_integration_health")
    
    sql = "SELECT service, is_healthy, status_code, checked_at FROM public.integration_health_live ORDER BY service"
    result = await supa_query(sql)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def cron_status(failing_only: bool = False) -> str:
    """Get cron job status and recent results.
    
    Args:
        failing_only: Show only failing jobs
    """
    having = "HAVING COUNT(*) FILTER (WHERE d.status='failed') > 0" if failing_only else ""
    sql = f"""
    SELECT j.jobname, j.schedule,
      COUNT(*) FILTER (WHERE d.status='succeeded') as ok_24h,
      COUNT(*) FILTER (WHERE d.status='failed') as fail_24h,
      (SELECT d2.status FROM cron.job_run_details d2 
       WHERE d2.jobid=j.jobid ORDER BY d2.start_time DESC LIMIT 1) as last_status,
      MAX(d.start_time) as last_run
    FROM cron.job j
    LEFT JOIN cron.job_run_details d ON d.jobid=j.jobid AND d.start_time>NOW()-INTERVAL '24h'
    WHERE j.active
    GROUP BY j.jobname, j.jobid, j.schedule
    {having}
    ORDER BY fail_24h DESC, j.jobname
    LIMIT 50
    """
    result = await supa_query(sql)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def deploy_cf_worker(
    worker_name: str,
    worker_code: str,
    cron: str = ""
) -> str:
    """Deploy a Cloudflare Worker to the ofshore.dev account.
    
    Args:
        worker_name: Name for the worker (e.g. 'my-agent')
        worker_code: Full worker JavaScript/ESM code
        cron: Optional cron schedule (e.g. '*/5 * * * *')
    """
    import base64
    
    boundary = "----CFDeploy"
    metadata: dict = {
        "main_module": "worker.js",
        "compatibility_date": "2025-01-01",
    }
    if cron:
        metadata["triggers"] = {"crons": [cron]}
    
    body = (
        f"--{boundary}\r\nContent-Disposition:form-data;name=\"metadata\"\r\nContent-Type:application/json\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Disposition:form-data;name=\"worker.js\";filename=\"worker.js\"\r\n"
        f"Content-Type:application/javascript+module\r\n\r\n"
        f"{worker_code}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(
            f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/workers/scripts/{worker_name}",
            headers={
                "Authorization": f"Bearer {CF_TOKEN}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            content=body,
        )
        d = r.json()
    return json.dumps({"success": d.get("success"), "errors": d.get("errors", [])}, indent=2)


@mcp.tool()
async def publish_event(event_type: str, payload: dict) -> str:
    """Publish an event to the CognitiveMind real-time channel (Upstash + pg_notify).
    
    Args:
        event_type: Event type (e.g. 'task_completed', 'insight_found')
        payload: Event data
    """
    msg = {
        "e": event_type,
        "src": "mcp-client",
        "ts": int(datetime.now().timestamp() * 1000),
        **payload,
    }
    result = await upstash("LPUSH", "ch:mind_events", json.dumps(msg))
    await upstash("LTRIM", "ch:mind_events", "0", "999")
    return json.dumps({"published": event_type, "channel_depth": result}, indent=2)


@mcp.tool()
async def analyze_and_build(topic: str, auto_queue: bool = True) -> str:
    """Use Groq to analyze a topic, generate insights, and optionally queue for building.
    
    Args:
        topic: What to analyze (e.g. 'payment automation for Polish freelancers')
        auto_queue: Automatically add top recommendations to build queue
    """
    analysis = await groq(
        f"""Analyze this opportunity for ofshore.dev ecosystem: {topic}
        
        ofshore.dev stack: Supabase, Cloudflare Workers, n8n, Coolify, Rust, Groq AI, Upstash Redis.
        Target: Polish market, B2B/B2C SaaS, quick builds.
        
        Return JSON:
        {{
          "opportunity": "1-sentence description",
          "pain_intensity": 0.0-1.0,
          "market_size": "small/medium/large",
          "build_days": 1-30,
          "revenue_potential_eur": 0,
          "approach": "how to build it",
          "first_step": "exact first action",
          "why_now": "timing rationale",
          "risks": ["risk1", "risk2"]
        }}""",
        800,
        system="You are a senior product analyst. Return ONLY valid JSON."
    )
    
    try:
        data = json.loads(analysis.replace("```json", "").replace("```", "").strip())
    except:
        data = {"raw_analysis": analysis}
    
    if auto_queue and data.get("pain_intensity", 0) > 0.6:
        await supa_rpc("execute_sql_with_result", {
            "sql_query": f"""
            INSERT INTO public.autonomous_build_queue
              (build_type, title, description, auto_priority, assigned_being)
            VALUES
              ('feature', '{topic[:80].replace("'","''")}',
               '{json.dumps(data)[:300].replace("'","''")}',
               {data.get('pain_intensity', 0.6)}, 'Solomon.Arch')
            ON CONFLICT DO NOTHING
            """
        })
        data["queued"] = True
    
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Resources ──────────────────────────────────────────────────────────────────

@mcp.resource("ofshore://dashboard")
async def dashboard_resource() -> str:
    """Live system dashboard as a resource."""
    result = await supa_rpc("system_dashboard")
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


@mcp.resource("ofshore://insights/latest")
async def latest_insights() -> str:
    """Latest 10 research insights."""
    sql = """
    SELECT ri.researcher, ri.solution_name, ri.problem_statement,
           mc.recommendation, mc.score
    FROM public.research_insights ri
    LEFT JOIN public.monetization_checks mc ON mc.insight_id=ri.id
    ORDER BY ri.created_at DESC LIMIT 10
    """
    return json.dumps(await supa_query(sql), indent=2, default=str)


@mcp.resource("ofshore://kb/{key}")
async def kb_resource(key: str) -> str:
    """Read a key from the knowledge bus."""
    raw = await upstash("GET", f"kb:{key}")
    return raw or "{}"


# ── Prompts ────────────────────────────────────────────────────────────────────

@mcp.prompt()
async def morning_briefing() -> str:
    """Generate a morning briefing from system state."""
    dash = json.loads(await system_dashboard())
    return f"""Generate a morning briefing for Maciej based on this system state:

{json.dumps(dash, indent=2, ensure_ascii=False)}

Include:
1. Overall system health (emoji + 1 sentence)
2. What was built/happened overnight
3. Top 3 actions for today
4. Any warnings or issues
5. Research insights summary

Keep it concise, in Polish, use emojis."""


@mcp.prompt()
async def build_plan(item: str) -> str:
    """Generate a detailed build plan for a specific item."""
    return f"""Create a detailed build plan for: {item}

Context: ofshore.dev ecosystem (Supabase + CF Workers + n8n + Coolify + Rust)
Maciej is a solo developer. Prefer autonomous solutions.

Include:
1. Technical approach (what files, what services)
2. Supabase SQL if needed
3. CF Worker code if needed  
4. n8n workflow if needed
5. Estimated hours
6. First 3 concrete steps"""


if __name__ == "__main__":
    mcp.run()
