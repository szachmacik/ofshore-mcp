# ofshore-mcp

MCP Server giving Claude Desktop / Cursor full access to the ofshore.dev ecosystem.

## Tools (15)
- `system_dashboard` — live system health
- `get_research_insights` — market research from AI agents
- `get_build_queue` — current build pipeline
- `queue_build` — add items to autonomous build queue
- `run_researcher` — trigger AI market researchers
- `collect_insights` — collect pending AI responses
- `groq_ask` — direct Groq Llama-3.3-70b access (FREE)
- `kb_write` / `kb_read` / `kb_list` — shared knowledge bus
- `send_telegram` — message Maciej via Guardian bot
- `execute_sql` — direct Supabase SQL
- `integration_health` — live health checks
- `cron_status` — cron job monitoring
- `deploy_cf_worker` — deploy CF Workers
- `publish_event` — CognitiveMind real-time events
- `analyze_and_build` — AI analysis → auto-queue

## Claude Desktop config
```json
{
  "mcpServers": {
    "ofshore": {
      "command": "docker",
      "args": ["run", "-i", "--rm",
        "-e", "SUPABASE_URL=https://blgdhfcosqjzrutncbbr.supabase.co",
        "-e", "SUPABASE_SERVICE_KEY=YOUR_KEY",
        "-e", "GROQ_API_KEY=YOUR_GROQ_KEY",
        "-e", "UPSTASH_URL=YOUR_UPSTASH_URL",
        "-e", "UPSTASH_TOKEN=YOUR_TOKEN",
        "-e", "TELEGRAM_TOKEN=YOUR_BOT_TOKEN",
        "-e", "CF_API_TOKEN=YOUR_CF_TOKEN",
        "ghcr.io/szachmacik/ofshore-mcp:latest"
      ]
    }
  }
}
```
