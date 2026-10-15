# One free Trello Workspace per Project

Every Project's Trello board (ADR 0002) lives alone in a free Trello Workspace of its own, which the platform creates through the Trello API with its dedicated Trello account. Members and the Product Owner are added to the board only, never to the Workspace.

The free Trello plan allows at most 10 boards and 10 collaborators per Workspace, and pending invitations count. A semester has more than 10 Projects with 4–6 Members each, so one shared free Workspace would be full after the first two Projects. A Workspace per Project holds one board and at most the Members, the Product Owner, the owner account and a coach added by hand.

## Considered options

- **One paid Workspace** (Trello Standard, per user per month): tidier, with every board in one place, but VIVES has no such subscription and the platform would depend on someone paying for it.
- **One shared free Workspace**: not workable because of the limits above.

## Consequences

- The dedicated account owns, and is admin of, many Workspaces. If it were removed, every board would lose its owner, so it's an account of the team (later of VIVES), never someone's personal one.
- A half-made Workspace (its board failed) is deleted again, so a retry starts clean.
- Should VIVES ever get a paid Workspace, new boards can move there without changing who is invited or how.
