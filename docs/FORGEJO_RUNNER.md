# Forgejo Runner setup

The KeyVault workflow uses:

```yaml
runs-on: ubuntu-latest
```

If Actions stays in `waiting`, Forgejo does not have an online runner with the `ubuntu-latest` label.

## 1. Get a registration token

In Forgejo, open:

```text
cheezy / KeyVault > Settings > Actions > Runners
```

Create or copy the repository runner registration token.

## 2. Start a Docker runner

On the server that will run Forgejo Actions, create a folder:

```bash
mkdir -p /opt/forgejo-runner/data
cd /opt/forgejo-runner
```

Create `docker-compose.yml`:

```yaml
services:
  runner:
    image: code.forgejo.org/forgejo/runner:6
    container_name: forgejo-runner-keyvault
    restart: unless-stopped
    environment:
      DOCKER_HOST: unix:///var/run/docker.sock
    volumes:
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    command: >
      sh -c '
        if [ ! -f /data/.runner ]; then
          forgejo-runner register \
            --no-interactive \
            --instance https://forg.app.strubens.uk \
            --token "$${FORGEJO_RUNNER_TOKEN}" \
            --name keyvault-runner \
            --labels "ubuntu-latest:docker://ghcr.io/catthehacker/ubuntu:act-22.04";
        fi;
        forgejo-runner daemon
      '
```

Create `.env`:

```text
FORGEJO_RUNNER_TOKEN=paste-token-here
```

Start it:

```bash
docker compose up -d
docker compose logs -f runner
```

## 3. Re-run the workflow

Return to:

```text
cheezy / KeyVault > Actions
```

Re-run the waiting job or push a new commit. The runner should now appear online and accept jobs with the `ubuntu-latest` label.

## Notes

- This runner mounts `/var/run/docker.sock` so the workflow can build and push Docker images.
- Only use this runner for repositories you trust.
- The runner registration token is sensitive. Do not commit it to Git.
