# NiceGUI frontend as a separate app over the REST API

The team wants both backend and frontend in Python. We use FastAPI for the backend and NiceGUI for the frontend, deployed as two separate apps (two containers): the NiceGUI frontend talks to the backend only through its REST API over HTTP and never touches the database. This keeps a clear seam: business rules and authorization live in one place, the backend is tested through its API, and future integrations (GitHub, Trello, the social-media agent) and any other client reuse the same API.

## Considered Options

- **NiceGUI mounted inside the FastAPI app**, pages calling services directly: one container and less plumbing, but UI and business logic blur and the REST API becomes an afterthought.
- **Jinja2 templates + HTMX**: most control over the VIVES look, but the team would mostly be writing HTML/CSS, not Python.
- **Reflex**: compiles Python to React and needs a Node.js build step; too heavy for the 4 GB VM.
- **Streamlit**: built for dashboards, reruns the whole script per interaction and has weak multi-user auth.
