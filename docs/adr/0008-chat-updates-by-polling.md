# Chat updates by polling

An open Project Chat (spec #91) asks the backend every 2 seconds for the messages after the last one it shows, and the navigation asks every 10 seconds for the Unread count. The backend doesn't push anything: the frontend keeps calling its REST API, as for every other screen (ADR 0003).

The browser already has a live WebSocket to the NiceGUI frontend, so whatever the frontend learns appears at once. Only the step from the frontend to the backend is polled. With a few dozen people in open chats that is a few dozen small, indexed queries per second, which the VM handles easily.

## Considered options

- **Push from the backend** (WebSocket or server-sent events between backend and frontend): new messages without the 2-second delay, but a second kind of connection to keep alive across Deploys, and the backend would have to know which pages are open.
- **Sharing messages inside the frontend process** (one NiceGUI app, so pages could notify each other): fast, but it only sees messages sent through this frontend, and it puts Chat logic in the frontend instead of behind the API.

## Consequences

- A message from someone else appears within about 2 seconds; the sender sees their own at once.
- "Is typing…" (#97) uses the same polling, and the backend keeps it in memory, which works because the backend runs as one process. If it ever runs as several workers, typing has to move to the database.
- Polling stops when the page closes, so idle tabs cost nothing more than the 10-second badge check.
