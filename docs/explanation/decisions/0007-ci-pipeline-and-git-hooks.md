# 0007. CI pipeline and git hooks

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

`mise run check` was the only gate, and only a person or an agent ran it. No
CI workflow was in the repository, so a pull request could merge without the
gate. No check looked for secrets in commits or for security problems in
workflows. Commit messages had to follow Conventional Commits, but no tool
checked them.

A CI pipeline is also a supply-chain target. A workflow can run a third-party
action at a tag that its owner can move, and the default `GITHUB_TOKEN` can
have write permissions.

Alternatives considered:

- **pre-commit (Python framework) for hooks.** It downloads hook environments
  for each repository and needs its own version pins. Lefthook is one binary
  that mise can pin with the other tools.
- **Husky for hooks.** It needs Node in every clone and a `prepare` script. The
  Python-only developer does not need Node.
- **One CI job that runs `mise run check`.** It is simple, but a failure does not
  show which check failed, and the checks run one after the other.

## Decision

- **CI runs mise tasks.** Every CI job runs a task from `mise.toml`. CI has no
  check that you cannot run on your computer.
- **One required check.** The `CI OK` job depends on all other jobs and fails if
  one of them fails or is cancelled. Branch protection requires only `CI OK`.
- **Hardened workflows.** Every third-party action is pinned to a full commit
  SHA. The default token permission is `contents: read`. Checkout does not keep
  credentials. actionlint and zizmor check every workflow change.
- **Security scans.** gitleaks scans the full history in CI and the staged diff
  in pre-commit. CodeQL runs on pull requests and every week. Dependency review
  blocks pull requests that add a high-severity vulnerability.
- **Git hooks with lefthook.** `pre-commit` does fast checks on staged files
  only. `commit-msg` checks the Conventional Commit subject. `pre-push` stops
  pushes to `main`, then runs `mise run check`.
- **Pinned tools.** mise pins lefthook, gitleaks, actionlint, zizmor and
  shellcheck, so the hooks and CI use the same versions.

## Consequences

- A pull request cannot merge with a failed gate, if branch protection requires
  `CI OK`. A maintainer must set this in the GitHub settings.
- A push takes approximately 1 to 2 minutes longer, because pre-push runs the
  full gate. `LEFTHOOK=0` skips the hooks, but CI still runs every check.
- Dependabot must update the SHA pins. Without it, the pins become old.
- GitHub Actions checks code only. The Vercel Git integration deploys: a
  preview for each push and production for each push to `main`. Vercel does not
  wait for CI, so branch protection on `main` is the control that stops
  unchecked code from reaching production.
- CI does not build the Docker images, because no environment deploys them.
  The images are for local use with `mise run up`.
- The pipeline does not sign builds or make build provenance (SLSA). This is
  not necessary at the current stage. A later decision can add it.
- End-to-end tests are not part of the pipeline yet. Issue #8 tracks Playwright
  tests against the Vercel preview deployments.
- gitleaks can find false positives. The repository keeps reviewed exceptions in
  `.gitleaks.toml` (test directories) and `.gitleaksignore` (fingerprints).
