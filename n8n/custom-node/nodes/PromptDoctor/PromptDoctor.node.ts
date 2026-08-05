import type {
IExecuteFunctions,
IHttpRequestOptions,
INodeExecutionData,
INodeType,
INodeTypeDescription,
} from 'n8n-workflow';

import {
NodeConnectionTypes,
NodeOperationError,
} from 'n8n-workflow';

interface GeminiResponse {
candidates?: Array<{
content?: {
parts?: Array<{
text?: string;
}>;
};
finishReason?: string;
}>;
}

interface PromptIssue {
type: string;
description: string;
}

interface JudgeResult {
score: number;
issues: PromptIssue[];
reasoning: string;
}

interface PromptIteration {
iteration: number;
prompt: string;
executorOutput: string;
score: number;
issues: PromptIssue[];
reasoning: string;
revisedPrompt?: string;
}

interface PromptDoctorMemory {
issueCounts?: Record<string, number>;
}

function extractGeminiText(response: GeminiResponse): string {
const text = response.candidates?.[0]?.content?.parts
?.map((part) => part.text ?? '')
.join('')
.trim();

if (!text) {
throw new Error(
'Gemini returned no text. The response may have been blocked or incomplete.',
);
}

return text;
}

function removeCodeFence(value: string): string {
return value
.trim()
.replace(/^```(?:json)?\s*/i, '')
.replace(/\s*```$/i, '')
.trim();
}

function removeOuterQuotes(value: string): string {
const cleaned = removeCodeFence(value);

if (
cleaned.length >= 2 &&
((cleaned.startsWith('"') && cleaned.endsWith('"')) ||
(cleaned.startsWith("'") && cleaned.endsWith("'")))
) {
return cleaned.slice(1, -1).trim();
}

return cleaned;
}

function parseJudgeResult(value: string): JudgeResult {
const cleaned = removeCodeFence(value);

let parsed: Partial<JudgeResult>;

try {
parsed = JSON.parse(cleaned) as Partial<JudgeResult>;
} catch {
throw new Error(`The judge returned invalid JSON: ${cleaned}`);
}

const rawScore = Number(parsed.score);

if (!Number.isFinite(rawScore)) {
throw new Error('The judge response does not contain a valid score.');
}

const issues: PromptIssue[] = Array.isArray(parsed.issues)
? parsed.issues.map((issue) => ({
type: String(issue?.type ?? 'unspecified_issue'),
description: String(issue?.description ?? ''),
}))
: [];

return {
score: Math.max(0, Math.min(10, Math.round(rawScore))),
issues,
reasoning: String(parsed.reasoning ?? ''),
};
}

function getTopLessons(
memory: PromptDoctorMemory,
limit: number,
): string[] {
return Object.entries(memory.issueCounts ?? {})
.sort((first, second) => second[1] - first[1])
.slice(0, limit)
.map(([issueType, count]) => `${issueType} (${count} previous occurrences)`);
}

function updateMemory(
memory: PromptDoctorMemory,
issues: PromptIssue[],
): void {
if (!memory.issueCounts) {
memory.issueCounts = {};
}

for (const issue of issues) {
memory.issueCounts[issue.type] =
(memory.issueCounts[issue.type] ?? 0) + 1;
}
}

async function callGemini(
context: IExecuteFunctions,
model: string,
prompt: string,
jsonMode = false,
): Promise<string> {
const body: Record<string, unknown> = {
contents: [
{
role: 'user',
parts: [
{
text: prompt,
},
],
},
],
};

if (jsonMode) {
body.generationConfig = {
responseMimeType: 'application/json',
};
}

const options: IHttpRequestOptions = {
method: 'POST',
url:
`https://generativelanguage.googleapis.com/v1beta/models/` +
`${encodeURIComponent(model)}:generateContent`,
headers: {
'Content-Type': 'application/json',
},
body,
json: true,
};

const response =
(await context.helpers.httpRequestWithAuthentication.call(
context,
'geminiApi',
options,
)) as GeminiResponse;

return extractGeminiText(response);
}

function createJudgePrompt(
prompt: string,
executorOutput: string,
lessons: string[],
): string {
const lessonsSection =
lessons.length > 0
? `
COMMON WEAKNESSES LEARNED FROM PREVIOUS RUNS:
${lessons.map((lesson) => `- ${lesson}`).join('\n')}

Treat these only as hints. Evaluate the current prompt independently.
`
: '';

return `
You are the Judge inside a prompt-improvement agent.

Evaluate the quality of the PROMPT, not whether its generated answer is factually correct.

Score the prompt from 0 to 10.

A strong prompt should:
- clearly identify the task,
- provide sufficient context,
- avoid ambiguity and contradictions,
- specify the expected output format when appropriate,
- specify useful constraints such as length, tone, structure, or language.

Use the executor output only as evidence of weaknesses in the prompt.

Return valid JSON with exactly this structure:

{
  "score": 0,
  "issues": [
    {
      "type": "short_snake_case_name",
      "description": "Specific explanation of the weakness"
    }
  ],
  "reasoning": "Brief explanation of the score"
}

If the score is 8 or higher, return an empty issues array.

Do not rewrite the prompt and do not propose a new prompt.
${lessonsSection}

PROMPT UNDER EVALUATION:
"""
${prompt}
"""

OUTPUT PRODUCED BY THE PROMPT:
"""
${executorOutput}
"""
`.trim();
}

function createReviserPrompt(
prompt: string,
issues: PromptIssue[],
lessons: string[],
): string {
const issueText =
issues.length > 0
? issues
.map(
(issue) =>
`- [${issue.type}] ${issue.description}`,
)
.join('\n')
: '- Improve clarity and specificity while preserving the task.';

const lessonsSection =
lessons.length > 0
? `
Previously common weaknesses:
${lessons.map((lesson) => `- ${lesson}`).join('\n')}
`
: '';

return `
You are the Reviser inside a prompt-improvement agent.

Rewrite the original prompt to fix only the listed issues.

Rules:
- Preserve the original intended task.
- Keep the same language as the original prompt.
- Do not add unrelated requirements.
- Do not explain your changes.
- Return only the revised prompt.
- Do not wrap the revised prompt in quotation marks or markdown.
${lessonsSection}

ORIGINAL PROMPT:
"""
${prompt}
"""

ISSUES TO FIX:
${issueText}
`.trim();
}

export class PromptDoctor implements INodeType {
description: INodeTypeDescription = {
displayName: 'Prompt Doctor Agent',
name: 'promptDoctor',
group: ['transform'],
version: 1,
description:
'Iteratively evaluates and improves prompts using Gemini as executor, judge, and reviser',
defaults: {
name: 'Prompt Doctor Agent',
},
inputs: [NodeConnectionTypes.Main],
outputs: [NodeConnectionTypes.Main],
usableAsTool: true,
credentials: [
{
name: 'geminiApi',
required: true,
},
],
properties: [
{
displayName: 'Prompt',
name: 'prompt',
type: 'string',
typeOptions: {
rows: 6,
},
default: '',
required: true,
placeholder: 'Example: Explain machine learning',
description:
'The rough prompt to evaluate and improve. Expressions such as {{$json.prompt}} are supported.',
},
{
displayName: 'Gemini Model',
name: 'model',
type: 'options',
options: [
{
name: 'Gemini 3.5 Flash-Lite',
value: 'gemini-3.5-flash-lite',
},
{
name: 'Gemini 3.6 Flash',
value: 'gemini-3.6-flash',
},
{
name: 'Gemini Flash Latest',
value: 'gemini-flash-latest',
},
],
default: 'gemini-3.5-flash-lite',
description: 'The Gemini model used by all three agent roles',
},
{
displayName: 'Maximum Iterations',
name: 'maxIterations',
type: 'number',
typeOptions: {
minValue: 1,
maxValue: 5,
},
default: 3,
description:
'Maximum number of execute, judge, and revise cycles',
},
{
displayName: 'Score Threshold',
name: 'scoreThreshold',
type: 'number',
typeOptions: {
minValue: 1,
maxValue: 10,
},
default: 8,
description:
'The minimum judge score required for convergence',
},
{
displayName: 'Enable Memory',
name: 'enableMemory',
type: 'boolean',
default: true,
description:
'Whether to remember frequently detected issue types',
},
{
displayName: 'Memory Lesson Limit',
name: 'memoryLessonLimit',
type: 'number',
typeOptions: {
minValue: 1,
maxValue: 10,
},
default: 5,
displayOptions: {
show: {
enableMemory: [true],
},
},
description:
'Maximum number of learned issue types passed to the agent',
},
],
};

async execute(
this: IExecuteFunctions,
): Promise<INodeExecutionData[][]> {
const items = this.getInputData();
const returnData: INodeExecutionData[] = [];

for (
let itemIndex = 0;
itemIndex < items.length;
itemIndex++
) {
let originalPrompt = '';

try {
originalPrompt = (
this.getNodeParameter(
'prompt',
itemIndex,
'',
) as string
).trim();

if (!originalPrompt) {
throw new Error('Prompt cannot be empty.');
}

const model = this.getNodeParameter(
'model',
itemIndex,
'gemini-3.5-flash-lite',
) as string;

const maxIterations = this.getNodeParameter(
'maxIterations',
itemIndex,
3,
) as number;

const scoreThreshold = this.getNodeParameter(
'scoreThreshold',
itemIndex,
8,
) as number;

const enableMemory = this.getNodeParameter(
'enableMemory',
itemIndex,
true,
) as boolean;

const memoryLessonLimit = enableMemory
? (this.getNodeParameter(
'memoryLessonLimit',
itemIndex,
5,
) as number)
: 0;

const memory =
this.getWorkflowStaticData(
'node',
) as unknown as PromptDoctorMemory;

if (!memory.issueCounts) {
memory.issueCounts = {};
}

let currentPrompt = originalPrompt;
let converged = false;
let stoppedReason = 'maximum_iterations_reached';
let finalScore = 0;

const iterations: PromptIteration[] = [];

for (
let iteration = 1;
iteration <= maxIterations;
iteration++
) {
const lessons = enableMemory
? getTopLessons(
memory,
memoryLessonLimit,
)
: [];

const executorOutput = await callGemini(
this,
model,
currentPrompt,
);

const judgePrompt = createJudgePrompt(
currentPrompt,
executorOutput,
lessons,
);

const judgeText = await callGemini(
this,
model,
judgePrompt,
true,
);

const judgment = parseJudgeResult(judgeText);

finalScore = judgment.score;

if (enableMemory) {
updateMemory(memory, judgment.issues);
}

const iterationRecord: PromptIteration = {
iteration,
prompt: currentPrompt,
executorOutput,
score: judgment.score,
issues: judgment.issues,
reasoning: judgment.reasoning,
};

if (judgment.score >= scoreThreshold) {
converged = true;
stoppedReason =
'score_threshold_reached';

iterations.push(iterationRecord);
break;
}

if (iteration === maxIterations) {
iterations.push(iterationRecord);
break;
}

const reviserPrompt = createReviserPrompt(
currentPrompt,
judgment.issues,
lessons,
);

const revisedPrompt = removeOuterQuotes(
await callGemini(
this,
model,
reviserPrompt,
),
);

if (!revisedPrompt) {
throw new Error(
'The reviser returned an empty prompt.',
);
}

iterationRecord.revisedPrompt =
revisedPrompt;

iterations.push(iterationRecord);
currentPrompt = revisedPrompt;
}

returnData.push({
json: {
...items[itemIndex].json,
originalPrompt,
finalPrompt: currentPrompt,
finalScore,
converged,
stoppedReason,
iterationCount: iterations.length,
model,
iterations,
learnedIssueTypes:
enableMemory
? getTopLessons(
memory,
memoryLessonLimit,
)
: [],
},
pairedItem: {
item: itemIndex,
},
});
} catch (error) {
const nodeError =
error instanceof Error
? error
: new Error(String(error));

if (this.continueOnFail()) {
returnData.push({
json: {
...items[itemIndex].json,
originalPrompt,
success: false,
error: nodeError.message,
},
pairedItem: {
item: itemIndex,
},
});

continue;
}

throw new NodeOperationError(
this.getNode(),
nodeError,
{
itemIndex,
},
);
}
}

return [returnData];
}
}
