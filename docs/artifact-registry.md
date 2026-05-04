---
title: Artifact Registry
product_area: ci-cd
tags: [artifacts, docker, containers, registry, packages]
---

# Artifact Registry

Helix Artifact Registry stores build outputs: Docker images, Python wheels, npm packages, and generic binaries.

## Docker Images

### Authenticating

```bash
# Get a registry token
helix registry login

# Or manually
echo $HELIX_TOKEN | docker login registry.helix.example \
  -u _token --password-stdin
```

### Pushing an Image

```bash
docker build -t registry.helix.example/{org}/{image}:{tag} .
docker push registry.helix.example/{org}/{image}:{tag}
```

In CI:
```yaml
- name: push-image
  uses: helix/docker-push@v1
  with:
    image: registry.helix.example/myorg/myapp
    tag: ${{ git.sha }}
```

### Pulling an Image

```bash
docker pull registry.helix.example/{org}/{image}:{tag}
```

### Image Tags

Best practices:
- Tag with `git.sha` for immutable builds: `myapp:a1b2c3d`
- Tag `latest` only for convenience — never use `latest` in production deployments
- Use semantic versions for releases: `myapp:1.4.2`

### Retention Policy

| Plan | Retention |
|------|-----------|
| Free | Last 5 tags per image |
| Pro | Last 50 tags, or 90 days |
| Enterprise | Configurable |

Set a custom policy per image:
```bash
POST /v1/registry/{org}/{image}/policy
{ "keep_last_n": 20, "keep_days": 30 }
```

## Python Packages

```bash
# Publish
python -m build
twine upload --repository helix dist/*

# Configure in pyproject.toml
[[tool.poetry.source]]
name = "helix"
url = "https://pypi.helix.example/{org}/simple/"
```

## npm Packages

```bash
# .npmrc
registry=https://npm.helix.example/{org}/

# Publish
npm publish
```

## Generic Artifacts

Upload any file as a build artifact:
```bash
POST /v1/builds/{build_id}/artifacts
Content-Type: multipart/form-data
file=@coverage.xml&name=coverage-report
```

Download:
```bash
GET /v1/builds/{build_id}/artifacts/{name}
```

## Security Scanning

Container images are automatically scanned for CVEs on push using Trivy. Scan results appear in the registry UI and are available via API:

```bash
GET /v1/registry/{org}/{image}/{tag}/scan-report
```

Configure blocking policies:
```yaml
# Settings → Registry → Scan Policy
block_on_severity: critical  # block pushes with critical CVEs
allow_exceptions:
  - CVE-2024-12345  # acknowledged, no fix available
```
