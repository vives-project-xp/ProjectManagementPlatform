# Project Management Platform

A central web application for managing and following up student projects within **Project Experience** at VIVES University of Applied Sciences (EO-ICT, Project 6).

**Product owner:** Ronny Mees

## Why

Running student projects today means many separate steps and tools: creating teams and projects, setting up repositories, granting students access, tracking tasks, following up progress — and a lot of valuable photo and video material gets lost along the way.

This platform centralizes and automates that work so coaches can spend more time on actual coaching, and turns weekly student updates into a visual project log and AI-assisted communication material.

## Scope

### MVP — Project management & automation (coaches)
- Create, edit and manage projects
- Add and manage students and coaches per project
- Automatically create and configure a repository, with the right users and permissions
- Automatically create and initialize a Trello board
- Authentication and authorization
- Overview of active and historical projects

### Project log & AI content (students)
- Weekly progress updates with photos, short videos and a short description
- Chronological timeline per project
- Media storage with metadata
- Generative AI (via API) proposes social-media content from the weekly updates
- Review step to check and edit generated content before it is published
- Attention to privacy, image rights and responsible use of AI

### Possible extensions
- **v2 — Budget & orders:** project budget, expenses/orders, linked documents, budget visualization
- **v3 — Evaluation & feedback:** evaluation moments, feedback per student/team, progress over time

A high-quality, usable MVP takes priority over implementing as many features as possible.

## How we work

This project is built with an **AI-assisted development workflow** (Claude Code + Matt Pocock's skills):

```
Discovery → Specification → Tickets → Implementation → Verification → Integration
```

- `/grill-with-docs` for discovery, `/to-spec` for the specification, `/to-tickets` for implementation issues
- `/implement #<issue>` — **one issue at a time**, always an unblocked one
- Every change goes through automated checks, manual review and functional testing before a pull request into `main`
- GitHub Issues is the tracker; durable decisions are recorded in `CONTEXT.md` and ADRs

## Tech stack

To be decided during discovery.

## Getting started

Setup, run, test and build instructions will be added once the stack is chosen.
