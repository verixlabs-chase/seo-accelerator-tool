# Native CMS Publishing

## Executive Intent
Allow direct content publishing to client CMS platforms starting with WordPress.

## Definitions
Publishing Adapter: CMS communication interface.
Editorial Workflow: Draft -> Review -> Approved -> Published.
Content Artifact: Structured content package.

## Requirements
- OAuth credential storage
- WordPress REST integration
- Draft and publish support
- Sync updates

## Required APIs
POST /api/v1/content/publish
GET /api/v1/content/status