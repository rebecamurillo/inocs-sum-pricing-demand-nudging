# API guidelines — the dynamic pricing demonstrator

The conventions every route follows. The contract itself is `contracts/openapi.json`,
generated from the code by `make contract`.

## Resources and routes

- Everything is under `/api/v1`. A breaking change needs `/api/v2`; within `v1`, fields are
  added, never renamed or removed.
- Paths name resources with plural nouns in kebab-case and never verbs:
  `/api/v1/city-instances/{id}/versions`. Nesting stops at one level below the owner.
- Methods mean what HTTP says: `GET` reads and changes nothing, `POST` creates, `PUT`
  replaces, `PATCH` changes part, `DELETE` removes. `GET`, `PUT` and `DELETE` are idempotent.
- JSON field names are `snake_case`. Identifiers are opaque strings. Times are ISO 8601 in
  UTC. A number that has a unit says it in its name (`radius_m`, `duration_s`).
- A route does three things: validate the request, call one use case, map the result. It
  holds no rule.

## Status codes

| Case | Code |
| --- | --- |
| Read or change succeeded with a body | `200` |
| Created | `201` with a `Location` header |
| Accepted, the work continues on the server | `202` with a `Location` header to the resource that reports its progress |
| Succeeded, nothing to return | `204` |
| The request is malformed or fails validation | `422` |
| The resource does not exist | `404` |
| The request conflicts with stored state (a rule between values, a version in use) | `409` |
| A component the request needs is unavailable (trip planner, solver) | `503` |

## Long work

Building a city instance or running the model takes minutes. Such a request returns `202`
at once; the work continues on the server and is a resource of its own with a state, the
running step, the finished steps and, on failure, the step and the reason. The client reads
it again to follow progress. Leaving the page changes nothing.

## Errors

Every error body is a problem document (RFC 9457, `application/problem+json`):

```json
{
  "type": "https://sum-project.eu/problems/component-unavailable",
  "title": "The trip planner is not reachable",
  "status": 503,
  "detail": "No answer from http://otp:8080/otp/gtfs/v1 within 2 s.",
  "code": "component_unavailable",
  "errors": [{ "field": "radius_m", "message": "must be greater than 0" }]
}
```

- `code` is a stable machine-readable name; the web app decides what to show from it.
- `title` and `detail` state the fact and its cause in plain English; `errors` is present
  for validation failures only.
- The domain raises typed errors; one mapping in `interface/http/` turns each type into its
  status and `code`. A route never builds an error response by hand and never raises an
  HTTP exception to report a rule: it lets the typed error through.
- Every error class has its entry in that mapping, for the exact class and never through a
  parent class; a test fails when one is missing. An
  error that reaches the mapping without an entry is a fault of the server: `500`.
- Every error the framework produces itself (unknown route, wrong method, unreadable body,
  failed validation) is a problem document too, and the contract documents `422` as one.
- A stack trace or an internal path never reaches a response.

## Lists

A list answers `{ "items": [...] }`, ordered and documented as such. Paging
(`limit`, `cursor`) is added to a list when its size is not bounded by design, not before.

## Routes outside the contract

- `GET /api/health` answers `200` as soon as the process serves requests. It checks nothing
  else and is what the containers' health checks call. What works and what does not is the
  business of `GET /api/v1/system-status`.
- `/api/test-control/…` is mounted only with the fake adapters and is used by the e2e suite
  alone (`docs/testing.md`).

Neither appears in `contracts/openapi.json`.

## Text in responses

A response carries identifiers and values, not sentences for the screen: the web app owns
the labels. `title` and `detail` of a problem are the exception, written for a person
reading a log or a failed request.
