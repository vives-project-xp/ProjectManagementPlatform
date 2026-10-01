# Two-table data model for the MVP: users and projects

The MVP stores everything in two tables, as the team asked: `users` (every person with a login, with Student-only fields left empty for other Roles) and `projects`. Because a Student is a Member of at most one Project, membership is a `project_id` column on the Student's row instead of a link table, and the Product Owner is a `product_owner_id` column on the Project. The Programme list was fixed in code for the MVP (only Electronics-ICT).

**Update (spec #24, #26):** the Programme list is now a third table, `programmes`, managed by the Superuser. `users.programme` still holds the Programme's name as text (no foreign key), so the Makers snapshot stays unchanged: the programmes service validates a Student's Programme against the table, renaming a Programme renames it for every User in the same transaction (never in the Makers), and a Programme can only be removed while no User has it.

## Consequences

- Membership history is not kept as rows. Instead, archiving a Project stores its Makers (a fixed snapshot of who made it) in a column on `projects` and frees its Students; restoring the Project does not re-add them.
- Adding a second Product Owner (the later Client role) or letting a Student join several Projects requires a schema change and data migration.
