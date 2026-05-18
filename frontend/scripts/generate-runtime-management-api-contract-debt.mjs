/* eslint-env node */
/* eslint-disable no-console */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendRoot, "..");
const outputPath = path.join(
  repoRoot,
  "api_contracts",
  "openapi",
  "runtime-management-api-contract-debt.generated.json",
);

const FOCUS_DIRS = [
  path.join(repoRoot, "futureagi", "accounts", "views"),
  path.join(repoRoot, "futureagi", "model_hub", "views"),
  path.join(repoRoot, "futureagi", "tracer", "views"),
];
const HTTP_DECORATOR_RE =
  /^\s*@(swagger_auto_schema|validated_request)\s*\((?<inline>.*)$/;
const DEF_RE = /^\s*def\s+(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(/;
const BROAD_REQUEST_SERIALIZERS = new Set(["AccountsJSONRequestSerializer"]);

function walkPythonFiles(dir) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (["__pycache__", "migrations"].includes(entry.name)) continue;
      files.push(...walkPythonFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".py")) {
      files.push(full);
    }
  }
  return files;
}

function countParenDelta(value) {
  let delta = 0;
  let inString = null;
  let escaped = false;
  for (const char of value) {
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (inString) {
      if (char === inString) inString = null;
      continue;
    }
    if (char === "'" || char === '"') {
      inString = char;
    } else if (char === "(") {
      delta += 1;
    } else if (char === ")") {
      delta -= 1;
    }
  }
  return delta;
}

function readDecorator(lines, startIndex) {
  const firstLine = lines[startIndex];
  const match = firstLine.match(HTTP_DECORATOR_RE);
  if (!match) return null;

  const decorator = match[1];
  const collected = [firstLine];
  let parenDepth = countParenDelta(firstLine);
  let index = startIndex + 1;
  while (parenDepth > 0 && index < lines.length) {
    collected.push(lines[index]);
    parenDepth += countParenDelta(lines[index]);
    index += 1;
  }

  return {
    decorator,
    text: collected.join("\n"),
    startLine: startIndex + 1,
    nextIndex: index,
  };
}

function nextFunctionName(lines, startIndex) {
  for (let i = startIndex; i < lines.length; i += 1) {
    const match = lines[i].match(DEF_RE);
    if (match) return match.groups.name;
    if (lines[i].trim() && !lines[i].trim().startsWith("@")) return null;
  }
  return null;
}

function serializerNames(text) {
  const names = new Set();
  const patterns = [
    /request_body\s*=\s*([A-Za-z_][A-Za-z0-9_]*)/g,
    /query_serializer\s*=\s*([A-Za-z_][A-Za-z0-9_]*)/g,
    /request_serializer\s*=\s*([A-Za-z_][A-Za-z0-9_]*)/g,
  ];
  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) {
      names.add(match[1]);
    }
  }
  return [...names].sort();
}

function decoratorUsesRuntimeValidation(record) {
  return record?.decorator === "validated_request";
}

function decoratorHasInputContract(record) {
  if (!record) return false;
  return (
    /\brequest_body\s*=/.test(record.text) ||
    /\bquery_serializer\s*=/.test(record.text) ||
    /\brequest_serializer\s*=/.test(record.text)
  );
}

function analyzeFile(filePath) {
  const rel = path.relative(repoRoot, filePath);
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  const decorators = [];

  for (let i = 0; i < lines.length; i += 1) {
    const record = readDecorator(lines, i);
    if (!record) continue;
    decorators.push({
      ...record,
      functionName: nextFunctionName(lines, record.nextIndex),
      serializers: serializerNames(record.text),
      rel,
    });
    i = record.nextIndex - 1;
  }

  return decorators;
}

const decorators = FOCUS_DIRS.flatMap((dir) =>
  walkPythonFiles(dir).flatMap(analyzeFile),
);
const validated = decorators.filter(decoratorUsesRuntimeValidation);
const directSwagger = decorators.filter(
  (record) => record.decorator === "swagger_auto_schema",
);
const docOnlyInputContracts = directSwagger.filter(decoratorHasInputContract);
const broadRequestContracts = decorators.filter((record) =>
  record.serializers.some((name) => BROAD_REQUEST_SERIALIZERS.has(name)),
);

const report = {
  generated_from: FOCUS_DIRS.map((dir) => path.relative(repoRoot, dir)),
  summary: {
    runtime_backed_validated_request_decorators: validated.length,
    direct_swagger_auto_schema_decorators: directSwagger.length,
    doc_only_input_contract_decorators: docOnlyInputContracts.length,
    broad_request_contract_decorators: broadRequestContracts.length,
  },
  doc_only_input_contract_decorators: docOnlyInputContracts.map((record) => ({
    path: record.rel,
    line: record.startLine,
    function: record.functionName,
    serializers: record.serializers,
  })),
  broad_request_contract_decorators: broadRequestContracts.map((record) => ({
    path: record.rel,
    line: record.startLine,
    function: record.functionName,
    serializers: record.serializers,
  })),
};

const nextJson = `${JSON.stringify(report, null, 2)}\n`;

if (process.argv.includes("--check")) {
  const current = fs.existsSync(outputPath)
    ? fs.readFileSync(outputPath, "utf8")
    : "";
  if (current !== nextJson) {
    console.error(
      "Runtime Management API contract debt report is stale. Run yarn contracts:generate.",
    );
    process.exit(1);
  }
  console.log("Runtime Management API contract debt report is up to date.");
} else {
  fs.writeFileSync(outputPath, nextJson);
  console.log(
    `Runtime Management API contract debt report written to ${path.relative(
      repoRoot,
      outputPath,
    )}.`,
  );
}
