# Local Secrets

Place server-local or workstation-local credential files here before starting the
stack when a provider requires mounted files.

Default Vertex AI service account file name:

```text
secrets/gcp-service-account.json
```

Docker Compose mounts this directory into the backend container at:

```text
/run/secrets
```

If `.env` contains:

```env
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-service-account.json
```

then this file must exist before Vertex-backed features are used:

```text
secrets/gcp-service-account.json
```

Repository rules:

- Only this README belongs in Git
- Real credential files stay local to the server or workstation
- Prefer Workload Identity Federation or another non-file credential flow when the deployment environment supports it
