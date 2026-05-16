# Admin UI Patterns

## Goals

The admin UI should default to a presentation-first workflow:

- show the current state before asking the operator to change it
- make on or off state obvious at a glance
- keep destructive and mutating actions deliberate
- move creation and editing into focused dialogs or dedicated edit states

This is the interaction model to use for users, robots, tokens, permissions, maintenance controls, settings, and future admin surfaces.

## Page structure

Each admin page should follow the same high-level layout:

- a page header that explains what the surface controls
- a presentation area that summarizes the current state
- a small set of primary actions
- edit or create flows that do not dominate the default page view

Prefer a readable overview first, then let the operator choose to edit. Avoid leading with large inline forms unless the page exists only to complete setup.

## Presentation vs edit

Default pages should be presentation views.

Presentation views should emphasize:

- status badges and current values
- last-known configuration and access state
- readable metadata and summaries
- concise action buttons such as `Edit`, `Enable`, `Disable`, `Reset password`, or `Delete`

Edit views should be separate from the default presentation state.

Use one of these patterns:

- a modal dialog for create, add, reset, and short edit tasks
- an explicit edit mode on the same page when the form is large enough that a modal would be cramped
- a dedicated detail page with its own edit action for profile-style entities

Do not mix an always-open edit form above the primary table unless the page is intentionally form-first.

## Toggle and state controls

Boolean and enabled or disabled state should use explicit stateful controls rather than ambiguous text buttons wherever practical.

Preferred patterns:

- use a switch or toggle row for stable boolean settings
- show the current state next to the control
- pair state changes with clear success or error feedback
- keep destructive actions visually distinct from reversible toggles

Examples in this project include:

- enabling or disabling users
- public or private repository visibility
- future operator settings that are naturally boolean

## Dialog usage

Use dialogs for focused mutations:

- create user
- create robot or token
- add permission
- reset password
- confirm delete or disable actions that carry risk

Dialogs should:

- carry a clear title and short explanation
- validate before submit
- prevent accidental closure while a request is pending
- return the operator to the same page context after success

If a workflow needs multiple sections, dense tables, or long-form explanation, prefer a dedicated edit state over a modal.

## Profile-style entity pages

User-like entities should trend toward a profile pattern instead of a raw table row plus hidden actions.

A profile-style page should include:

- identity summary
- current status
- role or privilege summary
- related access objects such as permissions or tokens
- recent meaningful activity when available
- a small action cluster for edit, enable or disable, reset, and delete

This pattern is a better fit for users, robots, and any future repository detail administration surface.

## Table and list behavior

Tables remain useful for scanning, but they should behave as presentation layers:

- rows summarize the entity
- actions stay short and obvious
- row-level edits open dialogs or a dedicated edit state
- empty states explain the absence of data and offer one primary action

Avoid turning the table page itself into a full data-entry form plus a listing unless there is a strong reason.

## Current repo implications

The current codebase now follows this model across the primary admin surfaces:

- `admin-shell.jsx` uses a desktop sidebar and a top-sliding mobile command menu; non-admin users only see the repository browser entry.
- `users-panel.jsx` and `tokens-panel.jsx` use paginated presentation tables or cards, with create/reset/revoke work in dialogs or action menus.
- `user-profile-panel.jsx` and `robot-profile-panel.jsx` use profile-style detail pages for identity summary, related tokens, permissions, and recent activity.
- `robots-panel.jsx` uses cards and dialogs for robot creation and token issuance, while profile pages handle per-robot inspection.
- `permissions-panel.jsx` keeps the page in presentation mode, then uses a focused dialog with switches for pull, push, and delete-tag access.
- `settings-panel.jsx` presents current runtime settings in a detail list and uses one edit dialog for origin, UI timezone, page size, audit retention, automatic rebuild, and storage refresh interval.
- `maintenance`, `sessions`, `audit`, registry inbox, and repository tag views use mobile disclosure panels, pagination, or mobile card lists where dense desktop tables would be hard to use.
- `repository-visibility-panel.jsx` uses a switch for public/private state, and `repo-delete-panel.jsx` uses a confirmation dialog for destructive action.

Future admin work should preserve that shape: default to inspection first, keep mutation flows focused, and reuse the existing primitives instead of inventing page-local controls.

## Reusable primitives

As the admin UI grows, prefer shared primitives for:

- `Switch`
- `FormDialog`
- `ConfirmDialog`
- `DetailList`
- `ActionMenu`
- `Badge`
- `EmptyState`
- `Pagination`
- `MobileCollapsiblePanel`
- `MobileCardList`

The goal is consistent operator-facing behavior across the admin area, not one-off page-specific interaction rules.
