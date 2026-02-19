# Organization & Subaccount Model

## Executive Intent
Enable agency white-label deployment with strict multi-tenant separation and usage controls.

## Definitions
Organization: Parent agency account.
Subaccount: Client account under an organization.
RBAC: Role-based access control.
Quota Allocation: Usage budget distribution across subaccounts.

## Requirements
- organizations table
- subaccounts table
- org_users table
- Role system (Owner, Admin, Manager, Viewer)
- Branding metadata per organization
- Usage tracking per org and subaccount

## Required APIs
POST /api/v1/orgs
POST /api/v1/orgs/{id}/subaccounts
GET /api/v1/orgs/{id}/usage