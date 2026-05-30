# SonarQube integration

SonarQube is an **optional** static-analysis source for QALLM. When
configured, it contributes higher-fidelity, ISO/IEC 25010-aligned ratings
(reliability, security, maintainability) that the `iso25010_base` profile
can prefer over the Radon/Bandit proxies. When not configured, QALLM runs
exactly as before on Radon and Bandit. This is the complement-with-fallback
design: SonarQube never replaces the offline tools, it elevates fidelity
when present.

## Why SonarQube here

SonarQube organises its analysis around a quality model that mirrors
ISO/IEC 25010 (reliability, security, maintainability ratings on an A..E
scale). That makes it a natural backing for the 25010 base profile. It is
also a useful contrast for the thesis: SonarQube and its AI CodeFix close
the quality loop *statically*, suggesting fixes for issues found by static
analysis without executing the code. QALLM closes the loop by *execution*.
Running both on the same code is a direct demonstration of the verification
gap: logic bugs that pass static analysis (and that a static fix may
declare resolved) are still caught by QALLM's generated tests.

## Deployment: self-hosted Server (default)

The integration targets a self-hosted SonarQube Server, which suits
QALLM's access pattern (many short-lived, locally-analysed code variants
per run) better than a CI/CD-oriented hosted service.

### Option A: docker compose (recommended)

QALLM's `docker-compose.yml` ships SonarQube as an optional profile, so
the API and the SonarQube server come up together:

```
docker compose --profile sonarqube up
```

Then open http://localhost:9000 (admin/admin on first login, change the
password), generate a token under My Account -> Security, and set in
`.env`:

```
SONARQUBE_URL=http://sonarqube:9000
SONARQUBE_TOKEN=<your token>
```

Because both services share the compose network, the API reaches the
server at the `sonarqube` hostname. Restart the api service to pick up
the new `.env` values.

### Option B: standalone docker run

If you are not using the compose stack:

1. Start a server:

   ```
   docker run -d --name sonarqube -p 9000:9000 sonarqube:community
   ```

   Wait for it to come up at http://localhost:9000 (first boot takes a
   minute). Default credentials are admin/admin; change the password on
   first login.

2. Create a user token: My Account -> Security -> Generate Tokens.

3. Install the scanner CLI (`sonar-scanner`) and put it on PATH, or set
   `SONARQUBE_SCANNER` to its full path.

4. Configure QALLM via environment variables:

   ```
   export SONARQUBE_URL=http://localhost:9000
   export SONARQUBE_TOKEN=<your token>
   # SONARQUBE_SCANNER=/opt/sonar-scanner/bin/sonar-scanner   # if not on PATH
   ```

   With both URL and TOKEN set, `AnalysisManager` automatically includes
   the SonarQube analyzer; otherwise it is silently skipped.

## Switching to SonarCloud (config swap, no code change)

```
export SONARQUBE_URL=https://sonarcloud.io
export SONARQUBE_TOKEN=<sonarcloud token>
export SONARQUBE_ORGANIZATION=<your org key>
```

The analyzer uses the same Web API endpoints, so the only difference is
the URL, token, and organization. SonarCloud is free for public repos.

## What the analyzer does

For each code unit, when configured:

1. Materialises the unit into a throwaway project directory with a
   generated `sonar-project.properties`.
2. Runs `sonar-scanner`, which uploads analysis to the server.
3. Fetches issues (`/api/issues/search`) and measures
   (`/api/measures/component`): `reliability_rating`, `security_rating`,
   `sqale_rating` (maintainability), plus raw counts and coverage.

Issues are normalised to QALLM `Finding`s; the ratings are read by the
`sonar.reliability_rating` / `sonar.security_rating` /
`sonar.maintainability_rating` evaluators from `context["sonar_measures"]`.
On any error the analyzer logs a warning and contributes nothing, so a
flaky server never breaks a run.

## Status and remaining work

Implemented and tested: the analyzer, the normalizer, the conditional
registration, the rating evaluators (skip-when-absent), the config, and
the orchestrator wiring that runs SonarQube on the variant being judged
and places its measures into the evaluation context under
`sonar_measures`. When SonarQube is unconfigured every piece no-ops and
the pipeline runs unchanged on Radon/Bandit.

The only step not exercisable in CI is the **live scan path** (the
`sonar-scanner` call and the Web API round-trip), which needs a running
server. It is guarded so failures fall back rather than break a run; it
should be smoke-tested once against a real server with a known-buggy file
to confirm the measure keys and issue shapes match this code.

## Suggested thesis experiment

Run SonarQube AI CodeFix and QALLM on the same buggy sample
(`buggy_research_code.py`, functions that pass static analysis but contain
runtime logic bugs). Expected result: SonarQube reports the code clean or
applies fixes that do not address the logic bug, while QALLM's generated
tests catch them by execution. This is a direct, quantifiable contrast
between static and execution-based quality improvement.
