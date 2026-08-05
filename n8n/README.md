# n8n Homework — Prompt Doctor Agent Node

This folder packages [PromptDoctor](../README.md) — the iterative prompt-improvement
agent from the earlier homeworks — as a real, self-hosted **n8n custom node**, plus a
workflow that puts it to work behind a webhook.

## What's here

```
n8n/
├── docker-compose.yml   # self-hosted n8n instance (Part A)
├── custom-node/         # node source: build this yourself
│   ├── nodes/PromptDoctor/PromptDoctor.node.ts
│   ├── credentials/GeminiApi.credentials.ts
│   └── package.json / tsconfig.json / ...
├── custom/              # pre-built JS output, ready to mount as-is (Part B)
├── workflows/
│   └── Prompt-Doctor-API-Workflow.json   # the concept-rich workflow (Part C)
└── screenshots/
    └── screenshots.docx
```

## Part A — Self-hosting n8n

`docker-compose.yml` runs a real self-hosted n8n instance (not n8n Cloud) and mounts
`./custom` into n8n's custom-extensions folder:

```bash
cd n8n
docker compose up -d
```

Open `http://localhost:5678`, create your owner account, and you're on your own instance.

## Part B — The custom node

The agent is implemented as `PromptDoctor.node.ts`. It re-implements the
executor → judge → reviser loop from the original CLI agent, but calls the
**Gemini API** (instead of the Claude CLI) so it can run headless inside n8n:

1. **Executor** — runs the current prompt through Gemini.
2. **Judge** — scores the prompt 0–10 and returns structured issues, using the
   executor's output only as evidence (not for factual correctness).
3. **Reviser** — rewrites the prompt to fix exactly the issues the judge raised.
4. Repeats until the judge score hits the threshold or `maxIterations` is reached.
5. **Memory** — an optional running counter of issue types (via n8n's per-node
   static workflow data), fed back into the judge/reviser as hints on later runs,
   mirroring the Reflexion-style memory of the original agent.

Node details:
- Display name: **Prompt Doctor Agent** (`promptDoctor`)
- Configurable parameters: `Prompt` (supports expressions like `{{$json.prompt}}`),
  `Gemini Model`, `Maximum Iterations`, `Score Threshold`, `Enable Memory`,
  `Memory Lesson Limit`.
- Credentials: **Gemini API** (`geminiApi`) — the API key lives in n8n's credential
  store and is injected via the `x-goog-api-key` header. It is never hardcoded in
  the node or in workflow expressions.
- Takes items in via the main input, returns the original item's fields plus
  `finalPrompt`, `finalScore`, `converged`, `iterationCount`, and the full
  iteration trace as items the next node can use.

### Installing it on your own instance

You can either build it yourself, or use the pre-built output already in `custom/`.

**Option 1 — use the pre-built output (fastest):**
The `custom/` folder already contains the compiled node and credential. It's mounted
by `docker-compose.yml`, so `docker compose up -d` is enough — the node will appear
in the node picker as **Prompt Doctor Agent** (under the `CUSTOM` group, since it's
loaded as a loose custom node rather than a published npm package).

**Option 2 — build from source:**
```bash
cd n8n/custom-node
npm install
npm run build
# copy the compiled output into the folder n8n mounts as its custom directory
cp -r dist/nodes ../custom/nodes
cp -r dist/credentials ../custom/credentials
cd ..
docker compose restart
```

### Setting up the credential

In n8n: **Credentials → New → Gemini API**, paste an API key from
[Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key), and save. Select
that credential on the Prompt Doctor Agent node.

## Part C — The workflow

`workflows/Prompt-Doctor-API-Workflow.json` is a single combined flow (Option 1)
that uses the custom node and hits every required concept:

| Concept | Node(s) |
| --- | --- |
| Non-manual trigger | `Webhook` (POST `/prompt-doctor`) |
| External API call | `Search Wikipedia` (real public Wikipedia REST API) |
| Branching | `Route Agent Result` (`Switch`: Approved / Needs Review / Error) |
| Merging | `Merge Agent Results` |
| Looping | `Process Prompts One by One` (Split In Batches, size 1) |
| Filtering | `Keep Valid Prompts` (`Filter`, drops empty/invalid prompts) |
| Data shaping | `Normalize Request` / `Build Agent Input` (`Set`) + `Expand & Enrich Prompts` (`Code`) |
| Error handling | `Search Wikipedia` and `Prompt Doctor Agent` run with `continueErrorOutput`, routed to `Handle Agent Error` |
| Output action | `Respond to Webhook` |
| Sticky notes | 5 notes documenting each section of the flow |
| Credentials | `geminiApi` credential, nothing hardcoded |

**Import it:** n8n → **Workflows → Import from File** → select the JSON. Open the
`Prompt Doctor Agent` node and re-select (or create) your Gemini credential — the
credential reference in the export is instance-specific and won't carry over.

**Run it:**
```bash
curl -X POST http://localhost:5678/webhook/prompt-doctor \
  -H "Content-Type: application/json" \
  -d '{
    "prompts": [
      { "prompt": "write about dogs", "topic": "dogs" },
      { "prompt": "x", "topic": "" }
    ]
  }'
```
The second entry is intentionally invalid (too short, no topic) so you can see the
Filter node drop it, while the first flows through Wikipedia lookup → Prompt Doctor
Agent → routing → merge → webhook response.

## Screenshots / recording

`screenshots/screenshots.docx` shows the self-hosted instance running the workflow
end to end, with the Prompt Doctor Agent node in the node picker and in action.
