---
name: summarize
description: URL and YouTube summarization via the summarize CLI.
metadata: {"openclaw":{"requires":{"bins":["summarize"]},"homepage":"https://github.com/steipete/summarize"}}
---

# Summarize

Use the `summarize` CLI to summarize URLs and YouTube videos.

## Requirements
- `summarize` CLI (install with `npx -y @steipete/summarize` or `npm i -g @steipete/summarize`)
- Config at `~/.summarize/config.json` with an API provider

## Usage
- URL: `summarize "<url>" --plain`
- YouTube: `summarize "<youtube_url>" --youtube auto --plain`

## Output
Return a short summary and, when requested, key bullet points.
