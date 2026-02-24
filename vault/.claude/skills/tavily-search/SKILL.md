---
name: tavily-search
description: Web search and extraction via Tavily MCP tools.
metadata: {"openclaw":{"requires":{"bins":["npx"],"env":["TAVILY_API_KEY"]},"homepage":"https://github.com/tavily-ai/tavily-mcp"}}
---

# Tavily Search

Use Tavily MCP tools for web search, extraction, and crawling.

## Requirements
- `npx` (Node.js)
- `TAVILY_API_KEY` set in environment

## MCP Tools
- `mcp__tavily__tavily-search`
- `mcp__tavily__tavily-extract`
- `mcp__tavily__tavily-map`
- `mcp__tavily__tavily-crawl`

## Usage
1. Prefer `tavily-search` for targeted queries with `search_depth` and `max_results`.
2. Use `tavily-extract` to fetch clean text from a URL.
3. Use `tavily-map` for site structure discovery before crawling.
4. Use `tavily-crawl` only when necessary to traverse multiple pages.

## Output
Summarize results briefly, cite sources where possible, and keep payloads small.
