# Landscape 2027 (future extension)

A live, interactive map of the AI tooling ecosystem: agent frameworks, MCP servers, coding agents, eval tools. New ones appear weekly and nobody can keep up; this shows the shape of the field and what is rising.

## Reuse from Constellation
The same frontend and graph data format. Only the ingestion changes, which is the point: it proves the Source adapter idea (ADR 0001) generalises beyond local config.

## Ingestion
- GitHub search API: stars, topics, recent activity.
- Hacker News Algolia API: mentions and discussion volume.

## LangGraph shape
fetch → fan out `summarise_repo` (`Send`) → `categorise` → `trend_agent` (month-over-month growth) → export graph data.

## Visual encoding
- Node size: stars.
- Node brightness: growth this month.
- Clusters: category (orchestrators, MCP servers, coding agents, eval tools).

## Refresh
Weekly cron rebuild, deployed as a static site on Vercel.
