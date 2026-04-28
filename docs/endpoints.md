# Rocketlane API endpoint cheat-sheet

Compact map of the 64 endpoints. For request/response shapes, see `openapi.yaml`
in this same folder. Use this file to figure out which path to call; only open
the full YAML when you need the field schema.

**Base URL:** `https://api.rocketlane.com/api/1.0`
**Auth:** `api-key` header
**Pagination:** `pageSize` (max 100) + `pageToken`. Response includes `nextPageToken`.
**Filtering:** `field.operation=value` — operations: `eq`, `ne`, `gt`, `lt`, `ge`, `le`, `cn` (contains), `nc` (not contains).
**Rate limits:** 60/min for GET-all, 400/min for everything else.

## Tasks
- `GET /tasks` — list (filter by `taskStatus`, `assigneeId`, `projectId`, etc.)
- `GET /tasks/{id}` — get one
- `POST /tasks` — create
- `PUT /tasks/{id}` — update **(write — confirm)**
- `DELETE /tasks/{id}` — **(write — confirm)**
- `POST /tasks/{id}/assignees` / `.../assignees/remove` — manage assignees
- `POST /tasks/{id}/followers` / `.../followers/remove` — manage followers
- `POST /tasks/{id}/dependencies` / `.../dependencies/remove` — manage deps
- `POST /tasks/{id}/phase` — move task to a phase

## Projects
- `GET /projects` — list (filter by `projectStatus`, `customerId`, `ownerId`)
- `GET /projects/{id}` — get one
- `POST /projects` — create **(confirm)**
- `PUT /projects/{id}` — update **(confirm)**
- `DELETE /projects/{id}` — **(DOUBLE confirm — destructive)**
- `POST /projects/{id}/archive` — archive **(confirm)**
- `POST /projects/{id}/template/import` — apply a template **(confirm)**
- `GET /projects/{id}/members` / `POST` add / `.../members/remove`
- `GET /projects/{id}/placeholders` / `.../placeholders/assign` / `.../placeholders/unassign`

## Phases
- `GET /phases` — list (filter by `projectId`)
- `GET /phases/{id}` — get one
- `POST /phases` — create **(confirm)**
- `PUT /phases/{id}` — update **(confirm)**
- `DELETE /phases/{id}` — **(confirm)**

## Users
- `GET /users` — list
- `GET /users/{id}` — get one

## Spaces
- `GET /spaces` / `GET /spaces/{id}` — list / get
- `POST /spaces` — create **(confirm)**
- `PUT /spaces/{id}` — update **(confirm)**
- `DELETE /spaces/{id}` — **(confirm)**

## Space Documents
- `GET /space-documents` / `GET /space-documents/{id}` — list / get
- `POST /space-documents` — create **(confirm)**
- `PUT /space-documents/{id}` — update **(confirm)**
- `DELETE /space-documents/{id}` — **(DOUBLE confirm — destructive)**

## Time Tracking
- `GET /time-entries` — list
- `GET /time-entries/{id}` — get one
- `POST /time-entries/search` — advanced search
- `POST /time-entries` — create **(confirm)**
- `PUT /time-entries/{id}` — update **(confirm)**
- `DELETE /time-entries/{id}` — **(confirm)**
- `GET /time-entry-categories` — list categories

## Time-Offs
- `GET /time-offs` / `GET /time-offs/{id}`
- `POST /time-offs` — create **(confirm)**
- `PUT /time-offs/{id}` — update **(confirm)**
- `DELETE /time-offs/{id}` — **(confirm)**

## Resource Allocations
- `GET /resource-allocations` — list (the only endpoint in this category)

## Invoices
- `GET /invoices` / `GET /invoices/{id}`
- `POST /invoices/{id}/line-items` — manage lines **(confirm)**
- `POST /invoices/{id}/payments` — record payment **(confirm)**
- `DELETE /invoices/{id}` — **(DOUBLE confirm — destructive)**

## Fields (custom fields)
- `GET /fields` — list
- `GET /fields/{id}` — get one
- `POST /fields` — create **(confirm)**
- `PUT /fields/{id}` — update **(confirm)**
- `DELETE /fields/{id}` — **(confirm)**
- `GET /fields/{id}/options` / `POST /fields/{id}/options/add` — manage options

## Tips for resolving names → IDs

The user usually says "the Acme project" not "P-1042". Resolve like this:

```bash
# Project: customer / project name
python scripts/rocketlane_call.py GET /projects 'projectName.cn=Acme' 'pageSize=10'

# Task: by name within a project
python scripts/rocketlane_call.py GET /tasks 'projectId.eq=42' 'taskName.cn=kickoff'

# User: by email
python scripts/rocketlane_call.py GET /users 'emailId.eq=jane@acme.com'
```

If more than one match comes back, list candidates with their IDs and ask the
user to pick before continuing.
