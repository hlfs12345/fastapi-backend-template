# Project Instructions

## Project

This repository contains a multi-tenant SaaS application for:

* CRM
* messaging and campaigns
* sales and orders
* inventory and reservations
* GPS tracking

The first production use may involve only one tenant, but the system must remain multi-tenant by design.

The application targets:

* Web
* Android
* iOS

Desktop is not part of the MVP.

---

# Stack

## Frontend

* Flutter
* Dart

## Backend

* Python 3.13
* FastAPI
* Pydantic
* Pydantic Settings
* SQLAlchemy 2
* Alembic
* asyncpg
* Celery
* Redis

## Database

* PostgreSQL
* PostGIS

## Security

* OpenBao
* Transit Engine

## Infrastructure

* Docker Compose
* uv for Python dependency management

Do not introduce alternative frameworks, databases, queues, ORMs or major infrastructure components without explaining the need first.

---

# General Engineering Principles

Prefer:

* explicit code;
* simple designs;
* clear domain boundaries;
* database-enforced invariants;
* tests for business rules;
* incremental changes.

Avoid:

* premature abstractions;
* premature microservices;
* unnecessary design patterns;
* clever code;
* unnecessary dependencies;
* hidden side effects.

Do not implement functionality that was not requested merely because it may be useful later.

---

# Architecture

The backend starts as a modular monolith.

API and workers may run as separate processes/containers but share the same application/domain code.

Long-running operations must not execute synchronously inside HTTP requests.

Examples:

* campaigns;
* bulk messaging;
* CSV/Excel imports;
* reports;
* external API retries.

These operations should use workers/queues.

---

# Backend Layers

Use the following responsibilities.

## Routers

Responsible for:

* HTTP concerns;
* request parsing;
* dependencies;
* authorization entry points;
* response serialization.

Do not place business logic in routers.

## Services

Responsible for:

* business rules;
* workflows;
* transactions;
* domain orchestration.

## Repositories

Responsible for:

* persistence;
* SQLAlchemy queries;
* database access.

Repositories must not contain business decisions.

## Models

SQLAlchemy persistence models.

## Schemas

Pydantic request/response schemas.

Avoid generic base repositories/services unless repeated usage demonstrates a real need.

---

# Multi-Tenancy

Multi-tenancy is mandatory.

Tenant-owned entities must contain `tenant_id` unless there is a documented reason not to.

Never trust an arbitrary `tenant_id` supplied by the client.

Tenant context must come from authenticated and authorized application context.

Every query against tenant-owned data must be tenant-scoped.

Tests must cover tenant isolation.

The model must support:

* one user belonging to multiple tenants;
* one tenant containing multiple users.

Use:

* tenants
* users
* tenant_users

Do not duplicate user accounts per tenant.

---

# Authorization

The system will use roles and permissions.

Expected entities:

* roles
* permissions
* role_permissions

Prefer semantic permissions such as:

* contacts.view
* contacts.edit
* contacts.export
* contacts.view_sensitive
* campaigns.create
* campaigns.send
* stock.view
* stock.adjust
* tracking.view
* tracking.manage
* users.manage

Avoid business logic based on scattered checks such as:

```python
if user.role == "ADMIN":
```

Prefer permission checks.

---

# Legal Documents

Legal documents must be versioned and immutable.

Expected entities:

* legal_documents
* legal_document_versions
* legal_acceptances

Never represent legal acceptance only as a boolean.

A legal acceptance should be able to record:

* user;
* tenant;
* legal document version;
* accepted_at;
* IP;
* user agent;
* application platform;
* application version;
* actor role snapshot;
* acceptance scope;
* metadata.

Acceptance scope may be:

* USER
* TENANT

Previous legal document versions must never be overwritten.

---

# LGPD / Personal Data

Do not confuse:

* encryption;
* pseudonymization;
* anonymization.

Active customer/contact data should normally remain recoverable through authorized access and therefore should use encryption/pseudonymization.

True anonymization is intended for cases where identity no longer needs to be recoverable.

Never log PII unnecessarily.

Never expose encrypted database values directly to clients.

---

# Encryption

OpenBao Transit is the cryptographic service.

The application must not own or persist encryption keys.

Expected Transit keys:

## pii-encryption

Used for encryption/decryption.

Use tenant-specific cryptographic context when applicable.

## pii-search

Used for HMAC/blind indexes.

Keys must never be stored in:

* source code;
* Flutter;
* PostgreSQL;
* Git;
* versioned configuration.

The backend should use a restricted OpenBao identity/policy.

Never use the OpenBao root token from application code.

---

# Searchable PII

Exact searches for values such as:

* CPF;
* phone;
* email;

should use:

normalized value
→ HMAC/blind index
→ indexed database lookup

The plaintext value should be encrypted separately.

Do not use plain SHA-256 for low-entropy searchable identifiers.

Use keyed HMAC.

Search indexes remain protected/pseudonymized data and must not be treated as anonymous.

---

# Contacts

Expected domain entities include:

* contacts
* contact_pii
* contact_channels
* contact_addresses
* tags
* contact_tags
* contact_lists
* contact_list_members

`contacts` may represent:

* leads;
* prospects;
* customers;
* imported contacts.

Do not create a separate customer entity unless the business model requires it.

Channels may include:

* WHATSAPP
* SMS
* TELEGRAM
* EMAIL

---

# Messaging

Messaging providers must be abstracted behind application interfaces/services.

Do not spread Meta, Telegram or SMS-specific logic throughout the domain.

Expected entities:

* provider_connections
* message_templates
* campaigns
* campaign_recipients
* messages
* message_events
* consents
* suppressions

Campaigns and messages are different entities.

A campaign may produce thousands of recipients/messages.

`campaign_recipients` should preserve processing results.

Messages must support:

* INBOUND
* OUTBOUND

Message event history must be preserved.

Do not rely exclusively on a mutable current status.

---

# Suppression / Opt-Out

Opt-out must not delete a contact.

Use suppression records.

A contact that opted out must not automatically become eligible again because their phone/email appeared in a new import.

Suppression rules must be checked before sending.

---

# Imports

CSV/Excel imports must be asynchronous.

Expected entities:

* imports
* import_errors

Expected processing pipeline:

upload
→ parse
→ normalize
→ validate
→ deduplicate
→ check suppression
→ persist

Keep import statistics such as:

* total rows;
* processed;
* created;
* updated;
* duplicates;
* invalid;
* suppressed.

Phone numbers must be normalized before duplicate checks.

---

# Products

Expected entities:

* products
* product_variants

Inventory belongs to the product variant rather than directly to the product.

Do not store a single `stock` field on `products`.

---

# Inventory

Expected entities:

* stock_locations
* stock_balances
* stock_movements
* stock_reservations

Inventory changes must generate stock movement records.

Available quantity is conceptually:

`quantity_on_hand - quantity_reserved`

Expected reservation statuses:

* ACTIVE
* CONSUMED
* RELEASED
* EXPIRED

Operations involving orders, reservations and stock must use appropriate database transactions.

Design against race conditions and overselling.

---

# Orders

Expected entities:

* orders
* order_items

Order/encomenda currently means:

customer request
→ order
→ optional reservation
→ payment
→ preparation
→ delivery

Do not introduce industrial production/MRP complexity unless requested.

---

# CRM

Expected entities include:

* pipelines
* pipeline_stages
* opportunities

Keep CRM domain logic separate from messaging and inventory logic even when workflows interact.

---

# GPS Tracking

Expected entities:

* tracked_assets
* trackers
* tracker_assignments
* tracker_positions

A tracker must not permanently belong directly to a vehicle/object.

Assignments preserve history.

Tracked asset types may include:

* VEHICLE
* PRODUCT
* PACKAGE
* EQUIPMENT
* OTHER

`tracker_positions` should use PostGIS.

Expected fields may include:

* tracker_id;
* recorded_at;
* position;
* latitude;
* longitude;
* speed;
* heading;
* altitude;
* battery_level;
* gps_valid;
* raw_data.

Important indexes:

* tracker_id + recorded_at;
* GiST spatial index on position.

Do not add TimescaleDB until actual data volume justifies it.

---

# Database Rules

All schema changes must use Alembic migrations.

Do not rely on manual database changes.

Use database features to enforce invariants when appropriate:

* foreign keys;
* unique constraints;
* check constraints;
* indexes;
* transactions.

Use `TIMESTAMPTZ` where appropriate.

Store backend timestamps in UTC.

Prefer UUID for externally visible/main business entities.

BIGINT may be used for very high-volume internal/event tables where appropriate.

---

# Deletion

Avoid hard deletion of auditable business records.

Prefer mechanisms such as:

* status;
* deleted_at;
* anonymized_at.

Hard delete only when it is explicitly appropriate.

---

# Audit

Use audit records for security and business-relevant actions.

Examples:

* inventory adjustment;
* campaign start/cancel;
* order cancellation;
* sensitive data access;
* administrative changes.

Audit logs do not replace domain history tables.

For example:

* message_events records messaging history;
* stock_movements records inventory history;
* legal_acceptances records legal history.

---

# Logging

Logs must never contain:

* passwords;
* OpenBao credentials;
* API tokens;
* encryption keys;
* CPF;
* full phone numbers;
* other unnecessary PII.

Prefer structured logging.

Include correlation/request identifiers where useful.

---

# Error Handling

Do not expose stack traces or internal secrets to clients.

Use consistent application errors and HTTP mapping.

External integrations must be treated as unreliable.

Design for:

* retries;
* timeouts;
* idempotency;
* duplicate webhooks;
* partial failures.

---

# Testing

Do not create, generate or add new tests unless the user explicitly requests them.
This restriction also applies to regression tests for bug fixes.
Existing tests may still be run when relevant to validate a change.

Tests are especially important for:

* tenant isolation;
* permissions;
* inventory reservations;
* concurrent stock operations;
* suppression;
* duplicate detection;
* encryption;
* blind indexes;
* legal acceptance;
* campaigns;
* transactions.

When fixing a business-rule bug, only add a regression test if the user explicitly requests it.

---

# Docker / Development

Local development runs on Windows using Docker Desktop + WSL2.

Infrastructure is defined through `compose.yaml`.

Expected services initially:

* postgres;
* redis;
* openbao.

Later:

* api;
* worker.

Do not instruct the user to install PostgreSQL, Redis or OpenBao directly on Windows.

Never run or recommend:

```bash
docker compose down -v
```

without explicitly warning that it destroys volumes/data.

---

# Dependencies

Before adding a new dependency:

1. verify that the standard library or existing dependency cannot reasonably solve the problem;
2. explain why the dependency is needed;
3. prefer maintained and widely used libraries.

Do not add dependencies silently.

---

# Change Discipline

Before substantial changes:

1. inspect the existing implementation;
2. identify affected modules;
3. make the smallest coherent change;
4. avoid unrelated refactors;
5. run relevant tests;
6. report important design decisions.

Do not rewrite working modules merely to match personal stylistic preferences.

---

# Coding Style

Prefer:

* descriptive names;
* explicit types;
* short cohesive functions;
* clear transactions;
* obvious control flow.

Avoid:

* excessive inheritance;
* metaprogramming;
* magic behavior;
* overly generic helpers;
* premature frameworks inside frameworks.

The codebase should remain understandable to an experienced developer reviewing generated code.

---

# Agent Workflow

When implementing a non-trivial feature:

1. read this file;
2. inspect relevant code;
3. state a short implementation plan;
4. mention meaningful architectural decisions;
5. implement;
6. run tests/lint/type checks applicable to the change;
7. summarize:

   * changed files;
   * tests executed;
   * migrations created;
   * remaining risks or decisions.

Do not ask for confirmation for routine implementation details already covered by this document.

Ask before making decisions that materially change:

* architecture;
* security model;
* persistence model;
* external providers;
* tenant model;
* legal data model.

---

# Current Implementation Order

Prefer developing the foundation in this order:

1. repository structure;
2. FastAPI application;
3. settings/configuration;
4. PostgreSQL connection;
5. SQLAlchemy;
6. Alembic;
7. Redis;
8. OpenBao integration;
9. health/readiness endpoints;
10. tenants;
11. users;
12. tenant_users;
13. authentication;
14. authorization/roles/permissions;
15. legal documents/EULA;
16. contacts and LGPD;
17. messaging;
18. CRM;
19. orders/inventory;
20. tracking.

Do not attempt to implement the entire product in a single task.
