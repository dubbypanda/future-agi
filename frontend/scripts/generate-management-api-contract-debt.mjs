/* eslint-env node */
/* eslint-disable no-console */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendRoot, "..");
const swaggerPath = path.join(
  repoRoot,
  "api_contracts",
  "openapi",
  "swagger.json",
);
const outputPath = path.join(
  repoRoot,
  "api_contracts",
  "openapi",
  "management-api-contract-debt.generated.json",
);

const MUTATION_METHODS = new Set(["post", "put", "patch"]);
const NON_RESPONSE_OPTIONAL_METHODS = new Set(["delete"]);
const NO_BODY_RESPONSE_STATUS = /^(204|205|304|3\d\d)$/;
const HTTP_METHODS = new Set([
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "head",
  "options",
]);

const swagger = JSON.parse(fs.readFileSync(swaggerPath, "utf8"));
const paths = swagger.paths || {};

function groupForPath(pathName) {
  return pathName.split("/").filter(Boolean)[0] || "root";
}

function operationId(operation, method, pathName) {
  return (
    operation.operationId ||
    `${method.toUpperCase()} ${pathName}`
      .replace(/[{}]/g, "")
      .replace(/[^a-zA-Z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
  );
}

function operationRecord(pathName, method, operation) {
  return {
    group: groupForPath(pathName),
    method: method.toUpperCase(),
    path: pathName,
    operation_id: operationId(operation, method, pathName),
    tags: operation.tags || [],
  };
}

const operations = Object.entries(paths).flatMap(([pathName, pathSpec]) =>
  Object.entries(pathSpec || {})
    .filter(([method]) => HTTP_METHODS.has(method))
    .map(([method, operation]) => operationRecord(pathName, method, operation)),
);

const operationsByKey = new Map(
  Object.entries(paths).flatMap(([pathName, pathSpec]) =>
    Object.entries(pathSpec || {})
      .filter(([method]) => HTTP_METHODS.has(method))
      .map(([method, operation]) => [
        `${method.toUpperCase()} ${pathName}`,
        { method, operation },
      ]),
  ),
);

function hasBodySchema(method, operation) {
  if (!MUTATION_METHODS.has(method)) return true;
  const parameters = operation.parameters || [];
  const hasBodyParameter = parameters.some(
    (parameter) => parameter.in === "body" && parameter.schema,
  );
  const hasFormDataContract = parameters.some(
    (parameter) => parameter.in === "formData" && parameter.type,
  );
  return hasBodyParameter || hasFormDataContract;
}

function hasResponseSchema(method, operation) {
  if (NON_RESPONSE_OPTIONAL_METHODS.has(method)) return true;
  const responses = operation.responses || {};
  const hasSchema = Object.values(responses).some(
    (response) => response?.schema,
  );
  if (hasSchema) return true;

  const statusCodes = Object.keys(responses);
  return (
    statusCodes.length > 0 &&
    statusCodes.every((statusCode) => NO_BODY_RESPONSE_STATUS.test(statusCode))
  );
}

const mutationEndpointsWithoutBodySchema = operations.filter((record) => {
  const { method, operation } = operationsByKey.get(
    `${record.method} ${record.path}`,
  );
  return !hasBodySchema(method, operation);
});

const operationsWithoutResponseSchema = operations.filter((record) => {
  const { method, operation } = operationsByKey.get(
    `${record.method} ${record.path}`,
  );
  return !hasResponseSchema(method, operation);
});

const byGroup = {};
for (const pathName of Object.keys(paths).sort()) {
  const group = groupForPath(pathName);
  byGroup[group] ||= {
    paths: 0,
    operations: 0,
    mutation_endpoints_without_body_schema: 0,
    operations_without_response_schema: 0,
  };
  byGroup[group].paths += 1;
}

for (const record of operations) {
  byGroup[record.group].operations += 1;
}
for (const record of mutationEndpointsWithoutBodySchema) {
  byGroup[record.group].mutation_endpoints_without_body_schema += 1;
}
for (const record of operationsWithoutResponseSchema) {
  byGroup[record.group].operations_without_response_schema += 1;
}

const report = {
  generated_from: path.relative(repoRoot, swaggerPath),
  summary: {
    paths: Object.keys(paths).length,
    operations: operations.length,
    mutation_endpoints_without_body_schema:
      mutationEndpointsWithoutBodySchema.length,
    operations_without_response_schema: operationsWithoutResponseSchema.length,
  },
  by_group: Object.fromEntries(Object.entries(byGroup).sort()),
  mutation_endpoints_without_body_schema: mutationEndpointsWithoutBodySchema,
  operations_without_response_schema: operationsWithoutResponseSchema,
};

const nextContents = `${JSON.stringify(report, null, 2)}\n`;

if (process.argv.includes("--check")) {
  if (!fs.existsSync(outputPath)) {
    console.error(
      `Missing generated Management API contract debt report: ${path.relative(
        repoRoot,
        outputPath,
      )}`,
    );
    process.exit(1);
  }
  const currentContents = fs.readFileSync(outputPath, "utf8");
  if (currentContents !== nextContents) {
    console.error(
      [
        "Management API contract debt report is stale.",
        `Run: yarn --cwd frontend contracts:generate`,
      ].join("\n"),
    );
    process.exit(1);
  }
  console.log("Management API contract debt report is up to date.");
} else {
  fs.writeFileSync(outputPath, nextContents);
  console.log(
    `Wrote ${path.relative(repoRoot, outputPath)} with ${
      report.summary.mutation_endpoints_without_body_schema
    } body-schema gaps and ${
      report.summary.operations_without_response_schema
    } response-schema gaps.`,
  );
}
