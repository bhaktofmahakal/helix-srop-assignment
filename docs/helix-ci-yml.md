---
title: .helix-ci.yml Reference
product_area: ci-cd
tags: [configuration, yaml, pipeline, steps, conditions]
---

# .helix-ci.yml Reference

Your pipeline is defined in `.helix-ci.yml` at the repo root.

## Minimal Example

```yaml
version: "1"

pipelines:
  test:
    trigger:
      - push: {branches: ["main", "feature/*"]}
    steps:
      - name: install
        run: pip install -e ".[dev]"
      - name: test
        run: pytest -q
```

## Full Schema

```yaml
version: "1"

# Shared environment variables (encrypted at rest)
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  PYTHON_VERSION: "3.11"

pipelines:
  build-and-deploy:
    # Trigger conditions (any match fires the pipeline)
    trigger:
      - push:
          branches: ["main"]
          paths: ["src/**", "Dockerfile"]
      - pull_request:
          target_branches: ["main"]
      - schedule:
          cron: "0 2 * * 1-5"  # weekdays at 2am UTC
      - manual: {}

    # Timeout for the entire pipeline
    timeout: 3600  # seconds

    # Runner selection
    runner:
      pool: standard  # or: gpu, large, self-hosted
      os: linux

    # Steps run sequentially by default
    steps:
      - name: checkout
        uses: helix/checkout@v2

      - name: setup-python
        uses: helix/setup-python@v1
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: install
        run: pip install -e ".[dev]"
        cache:
          key: pip-${{ hashFiles('pyproject.toml') }}
          path: ~/.cache/pip

      - name: lint
        run: ruff check .

      - name: test
        run: pytest -q --cov=src --cov-report=xml
        artifact:
          path: coverage.xml
          name: coverage-report

      - name: build-image
        run: docker build -t myapp:${{ git.sha }} .
        condition: ${{ git.branch == 'main' }}

      - name: push-image
        run: docker push registry.helix.example/myapp:${{ git.sha }}
        condition: ${{ git.branch == 'main' }}
        env:
          REGISTRY_TOKEN: ${{ secrets.REGISTRY_TOKEN }}

      - name: deploy
        run: helix deploy --env production --image myapp:${{ git.sha }}
        condition: ${{ git.branch == 'main' }}
        needs: [push-image]  # explicit dependency

# Parallel pipelines can run concurrently
  pr-checks:
    trigger:
      - pull_request: {}
    steps:
      - name: test
        run: pytest -q
      - name: type-check
        run: mypy src/
```

## Context Variables

| Variable | Description |
|----------|-------------|
| `${{ git.sha }}` | Full commit SHA |
| `${{ git.branch }}` | Current branch name |
| `${{ git.tag }}` | Tag name (if triggered by a tag) |
| `${{ pipeline.id }}` | Unique pipeline run ID |
| `${{ pipeline.trigger }}` | What triggered the run: `push`, `pr`, `schedule`, `manual` |
| `${{ secrets.NAME }}` | Encrypted secret from Settings → CI/CD Variables |

## Common Patterns

### Fan-out / fan-in (parallel steps)

```yaml
steps:
  - name: test-unit
    run: pytest tests/unit/
  - name: test-integration
    run: pytest tests/integration/
    parallel_group: tests  # runs concurrently with test-unit
  - name: report
    run: ./merge-coverage.sh
    needs: [test-unit, test-integration]  # waits for both
```

### Matrix builds

```yaml
steps:
  - name: test
    run: pytest -q
    matrix:
      python: ["3.10", "3.11", "3.12"]
      os: [linux, macos]
```

### Conditional steps

```yaml
- name: notify-slack
  run: ./notify.sh
  condition: ${{ pipeline.status == 'failed' && git.branch == 'main' }}
```
