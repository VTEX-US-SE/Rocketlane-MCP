#!/usr/bin/env node
/**
 * Rocketlane MCP Server
 * Exposes all 64 Rocketlane REST API endpoints as MCP tools.
 *
 * Setup: Set the ROCKETLANE_API_KEY environment variable before starting.
 *
 * Authentication: API key via 'api-key' header on every request.
 * Base URL: https://api.rocketlane.com/api/1.0
 *
 * Rate Limits:
 *   - GET-all endpoints: 60 req/min
 *   - All others: 400 req/min
 *
 * Docs: https://developer.rocketlane.com
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// ─── Config ──────────────────────────────────────────────────────────────────

const API_KEY = process.env.ROCKETLANE_API_KEY;
const BASE_URL = "https://api.rocketlane.com/api/1.0";

if (!API_KEY) {
  console.error(
    "[rocketlane-mcp] ERROR: ROCKETLANE_API_KEY environment variable is not set."
  );
  process.exit(1);
}

// ─── HTTP Helper ─────────────────────────────────────────────────────────────

async function rocketlaneRequest(method, path, body = null, query = {}) {
  const url = new URL(`${BASE_URL}${path}`);
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });

  const options = {
    method,
    headers: {
      "api-key": API_KEY,
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  };

  const res = await fetch(url.toString(), options);
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }

  if (!res.ok) {
    throw new Error(
      `Rocketlane API error ${res.status}: ${JSON.stringify(data)}`
    );
  }
  return data;
}

// ─── Tool Definitions ─────────────────────────────────────────────────────────

const TOOLS = [
  // ── TASKS ──────────────────────────────────────────────────────────────────
  {
    name: "get_all_tasks",
    description:
      "Get all tasks. Supports pagination (pageSize max 100, pageToken) and filtering using field.operation=value syntax.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number", description: "Number of records per page (max 100)" },
        pageToken: { type: "string", description: "Pagination token from previous response" },
        filter: { type: "string", description: "Filter expression, e.g. 'status.eq=OPEN'" },
      },
    },
  },
  {
    name: "get_task",
    description: "Get a single task by its ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_task",
    description: "Create a new task in Rocketlane.",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Task fields: name, projectId, phaseId, assigneeIds, dueDate, startDate, status, priority, description, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "update_task",
    description: "Update an existing task by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "Fields to update on the task" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_task",
    description: "Delete a task by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "add_task_assignees",
    description: "Add one or more assignees to a task.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { assigneeIds: ['user-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "remove_task_assignees",
    description: "Remove assignees from a task.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { assigneeIds: ['user-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "add_task_followers",
    description: "Add followers to a task.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { followerIds: ['user-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "remove_task_followers",
    description: "Remove followers from a task.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { followerIds: ['user-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "add_task_dependencies",
    description: "Add dependencies to a task.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { dependencyIds: ['task-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "remove_task_dependencies",
    description: "Remove dependencies from a task.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { dependencyIds: ['task-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "move_task_to_phase",
    description: "Move a task to a different phase.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Task ID" },
        body: { type: "object", description: "e.g. { phaseId: 'phase-id-1' }" },
      },
      required: ["id", "body"],
    },
  },

  // ── FIELDS ─────────────────────────────────────────────────────────────────
  {
    name: "get_all_fields",
    description: "Get all custom fields. Supports pagination.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
      },
    },
  },
  {
    name: "get_field",
    description: "Get a custom field by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Field ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_field",
    description: "Create a new custom field.",
    inputSchema: {
      type: "object",
      properties: {
        body: { type: "object", description: "Field definition: name, type, entityType, etc." },
      },
      required: ["body"],
    },
  },
  {
    name: "update_field",
    description: "Update a custom field by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Field ID" },
        body: { type: "object", description: "Fields to update" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_field",
    description: "Delete a custom field by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Field ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "add_field_option",
    description: "Add an option to a select/multi-select custom field.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Field ID" },
        body: { type: "object", description: "e.g. { label: 'New Option' }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "update_field_option",
    description: "Update options on a custom field.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Field ID" },
        body: { type: "object", description: "Option update payload" },
      },
      required: ["id", "body"],
    },
  },

  // ── PROJECTS ───────────────────────────────────────────────────────────────
  {
    name: "get_all_projects",
    description: "Get all projects. Supports pagination and filtering.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string", description: "Filter expression" },
      },
    },
  },
  {
    name: "get_project",
    description: "Get a project by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_project",
    description: "Create a new project in Rocketlane.",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Project fields: name, customerId, startDate, dueDate, ownerId, status, templateId, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "update_project",
    description: "Update a project by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "Fields to update" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_project",
    description: "Delete a project by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "add_project_members",
    description: "Add members to a project.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "e.g. { memberIds: ['user-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "remove_project_members",
    description: "Remove members from a project.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "e.g. { memberIds: ['user-id-1'] }" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "assign_project_placeholders",
    description: "Assign placeholder roles to a user in a project.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "Placeholder assignment payload" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "unassign_project_placeholders",
    description: "Unassign placeholder roles from a user in a project.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "Placeholder unassignment payload" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "get_project_placeholders",
    description: "Get placeholder roles in a project.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "Filter/query payload (optional)" },
      },
      required: ["id"],
    },
  },
  {
    name: "archive_project",
    description: "Archive a project by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "Optional archive payload" },
      },
      required: ["id"],
    },
  },
  {
    name: "import_template_to_project",
    description: "Import a template into an existing project.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Project ID" },
        body: { type: "object", description: "e.g. { templateId: 'template-id-1' }" },
      },
      required: ["id", "body"],
    },
  },

  // ── PHASES ─────────────────────────────────────────────────────────────────
  {
    name: "get_all_phases",
    description: "Get all phases. Supports pagination.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string" },
      },
    },
  },
  {
    name: "get_phase",
    description: "Get a phase by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Phase ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_phase",
    description: "Create a new phase in a project.",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Phase fields: name, projectId, startDate, dueDate, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "update_phase",
    description: "Update a phase by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Phase ID" },
        body: { type: "object", description: "Fields to update" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_phase",
    description: "Delete a phase by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Phase ID" },
      },
      required: ["id"],
    },
  },

  // ── TIME-OFFS ──────────────────────────────────────────────────────────────
  {
    name: "get_all_time_offs",
    description: "Get all time-offs. Supports pagination.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string" },
      },
    },
  },
  {
    name: "get_time_off",
    description: "Get a time-off entry by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Time-off ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_time_off",
    description: "Create a time-off entry.",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Time-off fields: userId, startDate, endDate, reason, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "delete_time_off",
    description: "Delete a time-off entry by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Time-off ID" },
      },
      required: ["id"],
    },
  },

  // ── USERS ──────────────────────────────────────────────────────────────────
  {
    name: "get_all_users",
    description: "Get all users in the workspace. Supports pagination.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string" },
      },
    },
  },
  {
    name: "get_user",
    description: "Get a user by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "User ID" },
      },
      required: ["id"],
    },
  },

  // ── SPACES ─────────────────────────────────────────────────────────────────
  {
    name: "get_all_spaces",
    description: "Get all spaces (project portals). Supports pagination.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string" },
      },
    },
  },
  {
    name: "get_space",
    description: "Get a space by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Space ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_space",
    description: "Create a new space (customer portal).",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Space fields: name, projectId, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "update_space",
    description: "Update a space by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Space ID" },
        body: { type: "object", description: "Fields to update" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_space",
    description: "Delete a space by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Space ID" },
      },
      required: ["id"],
    },
  },

  // ── TIME TRACKING ──────────────────────────────────────────────────────────
  {
    name: "get_all_time_entries",
    description: "Get all time entries. Supports pagination and filtering.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string", description: "Filter expression, e.g. 'userId.eq=abc'" },
      },
    },
  },
  {
    name: "get_time_entry",
    description: "Get a time entry by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Time entry ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_time_entry",
    description: "Log a new time entry.",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Time entry fields: userId, taskId, projectId, date, hours, categoryId, notes, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "update_time_entry",
    description: "Update a time entry by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Time entry ID" },
        body: { type: "object", description: "Fields to update" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_time_entry",
    description: "Delete a time entry by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Time entry ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "search_time_entries",
    description: "Search time entries (deprecated endpoint, use get_all_time_entries with filters instead).",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
      },
    },
  },
  {
    name: "get_time_entry_categories",
    description: "Get all time entry categories for time logging.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
      },
    },
  },

  // ── SPACE DOCUMENTS ────────────────────────────────────────────────────────
  {
    name: "get_all_space_documents",
    description: "Get all space documents. Supports pagination.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string" },
      },
    },
  },
  {
    name: "get_space_document",
    description: "Get a space document by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Space document ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_space_document",
    description: "Create a new document in a space.",
    inputSchema: {
      type: "object",
      properties: {
        body: {
          type: "object",
          description: "Document fields: title, spaceId, content, etc.",
        },
      },
      required: ["body"],
    },
  },
  {
    name: "update_space_document",
    description: "Update a space document by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Space document ID" },
        body: { type: "object", description: "Fields to update" },
      },
      required: ["id", "body"],
    },
  },
  {
    name: "delete_space_document",
    description: "Delete a space document by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Space document ID" },
      },
      required: ["id"],
    },
  },

  // ── RESOURCE ALLOCATIONS ───────────────────────────────────────────────────
  {
    name: "get_all_resource_allocations",
    description: "Get all resource allocations across projects. Supports pagination and filtering.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string", description: "Filter expression, e.g. 'projectId.eq=abc'" },
      },
    },
  },

  // ── INVOICES ───────────────────────────────────────────────────────────────
  {
    name: "get_all_invoices",
    description: "Get all invoices. Supports pagination and filtering.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number" },
        pageToken: { type: "string" },
        filter: { type: "string" },
      },
    },
  },
  {
    name: "get_invoice",
    description: "Get an invoice by ID.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Invoice ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "get_invoice_payments",
    description: "Get all payments for a specific invoice.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Invoice ID" },
      },
      required: ["id"],
    },
  },
  {
    name: "get_invoice_line_items",
    description: "Get all line items for a specific invoice.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Invoice ID" },
      },
      required: ["id"],
    },
  },
];

// ─── Route Map: tool name → { method, pathFn } ────────────────────────────────

function buildRoute(method, pathFn) {
  return { method, pathFn };
}

const ROUTES = {
  // Tasks
  get_all_tasks: buildRoute("GET", () => "/tasks"),
  get_task: buildRoute("GET", ({ id }) => `/tasks/${id}`),
  create_task: buildRoute("POST", () => "/tasks"),
  update_task: buildRoute("PUT", ({ id }) => `/tasks/${id}`),
  delete_task: buildRoute("DELETE", ({ id }) => `/tasks/${id}`),
  add_task_assignees: buildRoute("POST", ({ id }) => `/tasks/${id}/assignees`),
  remove_task_assignees: buildRoute("POST", ({ id }) => `/tasks/${id}/assignees/remove`),
  add_task_followers: buildRoute("POST", ({ id }) => `/tasks/${id}/followers`),
  remove_task_followers: buildRoute("POST", ({ id }) => `/tasks/${id}/followers/remove`),
  add_task_dependencies: buildRoute("POST", ({ id }) => `/tasks/${id}/dependencies`),
  remove_task_dependencies: buildRoute("POST", ({ id }) => `/tasks/${id}/dependencies/remove`),
  move_task_to_phase: buildRoute("POST", ({ id }) => `/tasks/${id}/phase`),

  // Fields
  get_all_fields: buildRoute("GET", () => "/fields"),
  get_field: buildRoute("GET", ({ id }) => `/fields/${id}`),
  create_field: buildRoute("POST", () => "/fields"),
  update_field: buildRoute("PUT", ({ id }) => `/fields/${id}`),
  delete_field: buildRoute("DELETE", ({ id }) => `/fields/${id}`),
  add_field_option: buildRoute("POST", ({ id }) => `/fields/${id}/options/add`),
  update_field_option: buildRoute("POST", ({ id }) => `/fields/${id}/options`),

  // Projects
  get_all_projects: buildRoute("GET", () => "/projects"),
  get_project: buildRoute("GET", ({ id }) => `/projects/${id}`),
  create_project: buildRoute("POST", () => "/projects"),
  update_project: buildRoute("PUT", ({ id }) => `/projects/${id}`),
  delete_project: buildRoute("DELETE", ({ id }) => `/projects/${id}`),
  add_project_members: buildRoute("POST", ({ id }) => `/projects/${id}/members`),
  remove_project_members: buildRoute("POST", ({ id }) => `/projects/${id}/members/remove`),
  assign_project_placeholders: buildRoute("POST", ({ id }) => `/projects/${id}/placeholders/assign`),
  unassign_project_placeholders: buildRoute("POST", ({ id }) => `/projects/${id}/placeholders/unassign`),
  get_project_placeholders: buildRoute("POST", ({ id }) => `/projects/${id}/placeholders`),
  archive_project: buildRoute("POST", ({ id }) => `/projects/${id}/archive`),
  import_template_to_project: buildRoute("POST", ({ id }) => `/projects/${id}/template/import`),

  // Phases
  get_all_phases: buildRoute("GET", () => "/phases"),
  get_phase: buildRoute("GET", ({ id }) => `/phases/${id}`),
  create_phase: buildRoute("POST", () => "/phases"),
  update_phase: buildRoute("PUT", ({ id }) => `/phases/${id}`),
  delete_phase: buildRoute("DELETE", ({ id }) => `/phases/${id}`),

  // Time-Offs
  get_all_time_offs: buildRoute("GET", () => "/time-offs"),
  get_time_off: buildRoute("GET", ({ id }) => `/time-offs/${id}`),
  create_time_off: buildRoute("POST", () => "/time-offs"),
  delete_time_off: buildRoute("DELETE", ({ id }) => `/time-offs/${id}`),

  // Users
  get_all_users: buildRoute("GET", () => "/users"),
  get_user: buildRoute("GET", ({ id }) => `/users/${id}`),

  // Spaces
  get_all_spaces: buildRoute("GET", () => "/spaces"),
  get_space: buildRoute("GET", ({ id }) => `/spaces/${id}`),
  create_space: buildRoute("POST", () => "/spaces"),
  update_space: buildRoute("PUT", ({ id }) => `/spaces/${id}`),
  delete_space: buildRoute("DELETE", ({ id }) => `/spaces/${id}`),

  // Time Tracking
  get_all_time_entries: buildRoute("GET", () => "/time-entries"),
  get_time_entry: buildRoute("GET", ({ id }) => `/time-entries/${id}`),
  create_time_entry: buildRoute("POST", () => "/time-entries"),
  update_time_entry: buildRoute("PUT", ({ id }) => `/time-entries/${id}`),
  delete_time_entry: buildRoute("DELETE", ({ id }) => `/time-entries/${id}`),
  search_time_entries: buildRoute("GET", () => "/time-entries/search"),
  get_time_entry_categories: buildRoute("GET", () => "/time-entry-categories"),

  // Space Documents
  get_all_space_documents: buildRoute("GET", () => "/space-documents"),
  get_space_document: buildRoute("GET", ({ id }) => `/space-documents/${id}`),
  create_space_document: buildRoute("POST", () => "/space-documents"),
  update_space_document: buildRoute("PUT", ({ id }) => `/space-documents/${id}`),
  delete_space_document: buildRoute("DELETE", ({ id }) => `/space-documents/${id}`),

  // Resource Allocations
  get_all_resource_allocations: buildRoute("GET", () => "/resource-allocations"),

  // Invoices
  get_all_invoices: buildRoute("GET", () => "/invoices"),
  get_invoice: buildRoute("GET", ({ id }) => `/invoices/${id}`),
  get_invoice_payments: buildRoute("GET", ({ id }) => `/invoices/${id}/payments`),
  get_invoice_line_items: buildRoute("GET", ({ id }) => `/invoices/${id}/line-items`),
};

// ─── Server ───────────────────────────────────────────────────────────────────

const server = new Server(
  { name: "rocketlane-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: TOOLS };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;

  const route = ROUTES[name];
  if (!route) {
    return {
      content: [{ type: "text", text: `Unknown tool: ${name}` }],
      isError: true,
    };
  }

  try {
    const path = route.pathFn(args);
    const { id, body, pageSize, pageToken, filter, ...rest } = args;

    // Build query params for GET requests
    const query = {};
    if (pageSize) query.pageSize = pageSize;
    if (pageToken) query.pageToken = pageToken;
    if (filter) {
      // Parse "field.op=value" style filters
      const [key, value] = filter.split("=");
      if (key && value) query[key] = value;
    }

    const requestBody = route.method !== "GET" && route.method !== "DELETE"
      ? (body || rest || {})
      : null;

    const result = await rocketlaneRequest(route.method, path, requestBody, query);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${err.message}` }],
      isError: true,
    };
  }
});

// ─── Start ────────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[rocketlane-mcp] Server started. Listening on stdio.");
}

main().catch((err) => {
  console.error("[rocketlane-mcp] Fatal error:", err);
  process.exit(1);
});
