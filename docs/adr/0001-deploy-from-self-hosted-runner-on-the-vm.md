# Deploy from a self-hosted runner on the VM

The deployment VM (`10.20.10.33`) is only reachable on the VIVES network, so GitHub-hosted runners cannot SSH into it. We deploy with a self-hosted GitHub Actions runner installed on the VM itself, which builds the Docker images locally with Docker Compose (no image registry) and serves the app behind Caddy with an internally signed certificate on the bare IP until VIVES IT provides a hostname. Lint and tests run on GitHub-hosted runners for every pull request.

## Consequences

- The repository is public, so the self-hosted runner only runs jobs triggered by a push to `main`; it must never be used by `pull_request` workflows, where a fork could execute code on the VM. Fork pull requests from all outside contributors require approval before any workflow runs.
- Secrets live in a `.env` file on the VM, never in the repository.
- Browsers show a certificate warning until a real hostname and certificate exist.
