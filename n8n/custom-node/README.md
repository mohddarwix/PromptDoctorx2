# n8n-nodes-prompt-doctor-gemini

A custom n8n node that packages the [PromptDoctor](../../README.md) agent —
Gemini as executor, judge, and reviser, iterating until a prompt is good enough.

See [../README.md](../README.md) for the full homework write-up: how to self-host
n8n, build/install this node, set up the Gemini credential, and run the workflow
that uses it.

## Local development

```bash
npm install
npm run dev     # starts n8n with this node loaded and hot reload enabled
```

## Build

```bash
npm run build   # compiles nodes/ and credentials/ to dist/
```
