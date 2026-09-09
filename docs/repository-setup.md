# Repository setup: applied configuration and evidence

Recorded 2026-09-09 for `DSEgrp18/Web-Page`, per the "Setup completion evidence"
requirement in [CLAUDE.md](../CLAUDE.md).

This file records what was **actually applied to GitHub and verified**, not what
was intended. Committed configuration files do not by themselves protect a
branch; the server-side settings below were applied through the GitHub API, and
the enforcement test at the end was run against the live repository.

## Repository

| Property | Value |
| --- | --- |
| Repository | `DSEgrp18/Web-Page` |
| Visibility | Public |
| Organization plan | Free |
| Default branch | `main` |

Visibility matters here: branch rulesets are available on free-plan
organizations for **public** repositories only. Making this repository private
without upgrading the organization to Team would disable every branch rule
described below.

## Members and permissions

| Member | Organization role | Effective repository permission |
| --- | --- | --- |
| `heshannethmina` (owner) | Owner | Admin |
| `KusalPabasara` | Owner | Admin |
| `LasanaPahanga` | Owner | Admin |

**Least privilege is not yet satisfied, and this is a known open item.**

The direct repository collaborator grant for `KusalPabasara` and
`LasanaPahanga` was set to `push` (write). That change was accepted, but it has
no practical effect: all three members are **organization Owners**, and
organization ownership confers admin on every repository in the organization.
Repository-level permission cannot reduce it.

Reducing their effective permission to write requires changing their
*organization* role from Owner to Member, which affects the whole organization —
billing, settings, and every other repository — not just this one. That is a
team decision and has been left to the owner.

This is mitigated but not resolved by the ruleset below: because the ruleset has
an empty bypass list, the branch rules apply to organization owners too. They
cannot silently push to `main`. They can still edit or delete the ruleset
itself, which is recorded in the organization audit log.

## Branch ruleset

Ruleset `main branch protection` (id `22613529`), enforcement **active**,
targeting `~DEFAULT_BRANCH`, with an **empty bypass list** — nobody bypasses,
including the owner and the other organization owners.

| Rule | Setting |
| --- | --- |
| Pull request required | Yes |
| Required approvals | 1 |
| Dismiss stale approvals on push | Yes |
| Require Code Owner review | Yes |
| Require approval of the most recent push | Yes |
| Require review threads resolved | Yes |
| Allowed merge method | Squash only |
| Required status check | `ci`, pinned to the GitHub Actions app (id `15368`) |
| Require branch up to date before merge | Yes (strict policy) |
| Block force pushes | Yes (`non_fast_forward`) |
| Block branch deletion | Yes (`deletion`) |
| Require linear history | Yes |

GitHub additionally enabled `require_extra_approval_for_unattributed_changes` by
default on the pull request rule.

Pinning the required check to the GitHub Actions app means only GitHub Actions
can satisfy `ci`. Another integration cannot report a green status under that
name.

### Enforcement test

Configuration was not trusted on its own. A direct push to `main` was attempted
from the owner's account, which is an organization owner. The server rejected it:

```text
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - Changes must be made through a pull request.
remote: - Required status check "ci" is expected.
 ! [remote rejected] main -> main (push declined due to repository rule violations)
```

The local probe commit was discarded and `main` was reset to `origin/main`; no
probe commit exists in history.

Reading the rules that apply to `main` for the requesting user also returns all
five rules, confirming no bypass is in effect for owners.

## Merge and security settings

| Setting | State |
| --- | --- |
| Squash merge | Enabled (only permitted method) |
| Merge commits | Disabled |
| Rebase merge | Disabled |
| Auto-merge | **Disabled**, deliberately — merging stays a human decision |
| Delete branch on merge | Enabled |
| Squash commit title / message | Pull request title / body |
| Secret scanning | Enabled |
| Secret scanning push protection | Enabled |
| Dependabot alerts | Enabled |
| Dependabot automated security fixes | Enabled |
| Wiki | Disabled (unused surface) |

Squash-only merging with the pull request title and body keeps `main` linear and
readable, and preserves the pull request author as the commit author.

Not enabled: `secret_scanning_non_provider_patterns` was requested but reported
back as `disabled`, and `secret_scanning_validity_checks` remains disabled. Push
protection and provider-pattern scanning are active, which covers the main risk.
Secret scanning push protection was **not** live-tested; unlike the branch rules,
testing it would require pushing a real-looking credential.

## Committed configuration

| Path | Purpose |
| --- | --- |
| `.github/workflows/ci.yml` | CI; the aggregate `ci` job is the required check |
| `.github/CODEOWNERS` | Review routing; owner required for workflows and infrastructure |
| `.github/PULL_REQUEST_TEMPLATE.md` | Verification, accessibility, privacy, and rollback prompts |
| `.github/ISSUE_TEMPLATE/` | Task, bug, and accessibility forms; blank issues disabled |
| `.github/dependabot.yml` | Weekly GitHub Actions updates |
| `CONTRIBUTING.md` | Branch naming, commits, review expectations |
| `SECURITY.md` | Private vulnerability reporting |
| `scripts/verify-*.sh` | Checks run by CI and locally |
| `.gitattributes` | LF normalisation; byte-exact vendored tables |
| `.editorconfig` | Editor consistency |

Labels referenced by the issue forms were created: `task`, `accessibility`,
`dependencies`, `a11y-blocker`, `blocked`, and seven `area:` labels.

## CI

Workflow **CI** runs on pull requests and pushes to `main`, with
`permissions: contents: read` and `actions/checkout` pinned to commit
`3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1).

| Job | Checks |
| --- | --- |
| Vendored assets | FM-Abhaya tables match the SHA-256 values recorded in their README; 6 conversion cases present |
| Repository hygiene | No tracked model weights, audio, documents, or secrets; no file over 5 MiB; ignore rules intact |
| Shell scripts | ShellCheck at `--severity=style` |
| `ci` | Aggregate gate; fails if any dependency fails, is cancelled, **or is skipped** |

First run: [`34315776306`](https://github.com/DSEgrp18/Web-Page/actions/runs/34315776306)
on `chore/repo-governance` — all four jobs succeeded.

CI covers only what exists. There is no application code, so there are no unit
tests, type checks, frontend builds, container builds, or accessibility smoke
tests yet. These are added by the pull requests that introduce the code they
check. No required status name exists for a check that does not run.

## Open items

1. **Organization roles.** Reduce `KusalPabasara` and `LasanaPahanga` from
   organization Owner to Member if the team wants genuine least privilege.
2. **Per-area code owners.** `.github/CODEOWNERS` currently assigns every path to
   all three members, with the per-area split left as commented placeholders.
   Assign owners once the team agrees and the directories exist.
3. **Licence.** No `LICENSE` file; default copyright applies. Blocked on the
   unresolved CPML non-commercial question for the XTTS-v2 weights.
4. **Deployment environments.** No staging or production environment, protected
   environment, or deployment credentials are configured. Nothing is deployed.
5. **GPU smoke tests.** No trusted GPU runner is configured, so real-model
   synthesis tests do not run anywhere yet.
