# Work with CI and the git hooks

This guide tells you how to install the git hooks, fix a failed hook or CI job,
and change the pipeline. For the full list of hooks, jobs and tasks, see
[CLI and tasks](../reference/cli-and-tasks.md#git-hooks-lefthookyml).

## 1. Install the hooks

The hooks install when you run setup:

```bash
mise run setup
```

To install only the hooks, run:

```bash
mise run hooks:install
```

mise pins the hook tools (lefthook, gitleaks, actionlint, zizmor, shellcheck, semgrep).
Do not install them with Homebrew or another package manager. A different
version can give different results from CI.

## 2. Fix a failed pre-commit hook

The pre-commit hook checks only the staged files.

| Job | Failure | Fix |
| --- | --- | --- |
| `secrets` | gitleaks found a possible secret in the staged diff | Remove the secret from the file. Put real values in `.env`, which git ignores. If the secret was real, revoke it. |
| `whitespace` | Trailing whitespace or a conflict marker | Remove it, then stage the file again |
| `ruff` | A lint error that ruff cannot fix | Fix the error that ruff shows, then stage the file again |
| `eslint` | A lint error that eslint cannot fix | Fix the error that eslint shows, then stage the file again |
| `sast` | Semgrep found a security issue in the staged files | Fix the issue, or suppress a reviewed false positive with `# nosemgrep: <rule-id>` and a short reason |
| `workflows` | actionlint or zizmor found a problem in `.github/` | Run `mise run lint:actions` and fix each finding |

The `ruff` and `eslint` jobs fix what they can and stage the fixed files again.
Look at the staged diff before you push.

### Possible secret that is not a secret

Do not disable the scan. Do one of these:

- If the value is in a test, put the test in a `tests/` directory. The rules in
  `.gitleaks.toml` ignore test directories.
- If the value is in a commit that is already in history, add the fingerprint
  from the gitleaks report to `.gitleaksignore`, with a comment that tells why
  it is safe.

## 3. Fix a rejected commit message

The subject line must be a
[Conventional Commit](https://www.conventionalcommits.org):

```text
feat(engine): add canary token check
fix(api): return 409 when the save slot is full
docs: explain the pre-push hook
```

The permitted types are `feat`, `fix`, `docs`, `style`, `refactor`, `perf`,
`test`, `build`, `ci`, `chore` and `revert`. The scope is optional. To change
the message of the last commit, run `git commit --amend`.

## 4. Fix a failed pre-push hook

The pre-push hook does two things, in this sequence:

1. It stops a push to `main`. Push a branch and open a pull request.
2. It runs `mise run check`. To see the failure, run the task that failed, for
   example `mise run test:api`.

The full gate takes approximately 1 to 2 minutes. If nothing new is in the
push, lefthook does not run the hook.

## 5. Skip the hooks in an emergency

```bash
LEFTHOOK=0 git push
```

CI runs the same checks. A skipped hook does not let a failure into `main`.
Do not skip the hooks to hide a failure.

## 6. Fix a failed CI job

Each CI job runs a mise task. Run the same task on your computer:

| CI job | Local command |
| --- | --- |
| `Lint` | `mise run lint:py` and `mise run lint:web` |
| `Typecheck` | `mise run typecheck:py` and `mise run typecheck:web` |
| `Test (Python)` | `mise run test:engine`, `mise run test:api`, `mise run test:tooling` |
| `Test (web)` | `mise run test:web` |
| `Specs and contract` | `mise run spec:check` and `mise run contract:check` |
| `Build (web)` | `mise run build:web` |
| `Migrations` | `mise run db:check` |
| `Workflow security` | `mise run lint:actions` |
| `Secret scan` | `mise run secrets:scan` |
| `SAST (Semgrep)` | `mise run sast` |

`Dependency review` has no local command. It fails when a pull request adds a
dependency with a known vulnerability of high or critical severity. Update the
dependency to a fixed version.

`CI OK` fails when a different job fails or is cancelled. Fix that job first.

## 7. Change the pipeline

- **Add a check.** Add a mise task in `mise.toml` first. Then add a CI job that
  runs the task, and add the job to the `needs` list of `CI OK`.
- **Add a third-party action.** Pin it to a full commit SHA and put the version
  in a comment:

  ```yaml
  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  ```

  To find the SHA of a tag, run
  `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`.
- **Give a job more permissions.** Add a `permissions:` block to that job only.
  Do not change the `contents: read` default at the top of the workflow.
- **Update a tool version.** Change the pin in the `[tools]` table of
  `mise.toml`. CI and the hooks use the same pin.

After you change a file in `.github/`, run `mise run lint:actions`.

## 8. Deploy

Vercel deploys the application. The Vercel Git integration is connected to
this repository. It has two projects: `ai-shield` (web client) and
`ai-shield-backend` (gateway).

- Each push to a branch makes a preview deployment.
- Each push to `main` makes a production deployment.

No GitHub workflow deploys. Vercel shows the result of each deployment as a
commit status on the pull request.

Vercel does not wait for CI. A merge to `main` deploys to production at the same
time as CI runs on `main`. Branch protection (step 9) makes sure that CI passed
on the pull request before the merge.

## 9. Set up branch protection

Do this one time, in the GitHub repository settings, for the `main` branch:

1. Require a pull request before merging.
2. Require status checks to pass. Select **CI OK** and **Conventional Commit
   title** only. Do not select the other jobs: `CI OK` already includes them.
3. Block force pushes.
