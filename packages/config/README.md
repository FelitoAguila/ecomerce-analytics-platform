# config (`global-config`)

Shared settings foundation imported by every package. It loads one `.env` from
the workspace root and exposes the small pydantic models the services reuse.

```python
from config.settings import BigQuery, ConfigBase, GoldTableRefs, PostgresDB
from config.paths import workspace_root
```

## 1. `ConfigBase`

Every service's `Settings` subclasses `ConfigBase`:

```python
class Settings(ConfigBase):
    postgres_db: PostgresDB
    bigquery: BigQuery
```

- **One `.env` for the workspace.** `env_file` resolves to
  `<workspace>/.env`, not the current directory, so commands behave the same
  from the repo root or any package folder.
- **Nested keys use `__`.** `POSTGRES_DB__DSN` → `settings.postgres_db.dsn`,
  `BIGQUERY__PROJECT` → `settings.bigquery.project`.
- **`extra="ignore"`.** A service only declares the fields it consumes; keys
  meant for other services in the same `.env` are ignored.
- **OS env wins over `.env`.** Useful for containers and CI.

Required fields (no default) fail fast at startup with a pydantic validation
error, which is how missing credentials surface before any work starts.

## 2. `workspace_root()`

Finds the uv workspace root by walking up from `Path.cwd()` to the nearest
`pyproject.toml` containing `[tool.uv.workspace]`. Cached with `lru_cache`.
Used by `ConfigBase` (to locate `.env`) and by the ELT/Prefect runners (to set
the subprocess `cwd`).

## 3. Models

| Model | Fields | Used by |
|---|---|---|
| `PostgresDB` | `dsn` | `ecommerce_db`, `pipeline` |
| `BigQuery` | `project`, `location` (default `us-central1`), `keyfile` | `pipeline`, `dashboard` |
| `GoldTableRefs` | `source`, `fct_*` / `dim_*` / snapshot / intermediate table names | `dashboard` |

`BigQuery.keyfile` is validated at construction: the path is expanded,
resolved, and must exist, so a typo fails immediately instead of at query time.

`GoldTableRefs` keeps the serving layer config-driven: the dashboard reads
`<dataset>.<table>` names from `DASHBOARD__*` env vars (defaults match the dbt
datasets) instead of hardcoding them in SQL.

## 4. Adding a setting

1. Add a field (with a default when possible) to the owning model here or in
   the service's `config.py`.
2. Document the env key in the repo-root `.env.example`.
3. Read it through `get_settings()` — do not read `os.environ` directly.

See [`docs/oltp-guide.md`](../../docs/oltp-guide.md),
[`docs/dlt-pipeline.md`](../../docs/dlt-pipeline.md), and
[`docs/dashboard.md`](../../docs/dashboard.md) for how each service uses these
models.
