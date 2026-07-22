# Contributing to Maintainer Burnout Guard

First off — thank you. This project exists to protect maintainers, and the irony of burning out contributors in the process is not lost on us. We keep this process lightweight by design.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Branch & Commit Conventions](#branch--commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [What We Won't Accept](#what-we-wont-accept)

---

## Code of Conduct

Be direct. Be kind. Assume good intent. We don't have a formal CoC document, but the short version is: treat people the way you'd want to be treated if you were the one maintaining this at 11pm on a Tuesday.

---

## How to Contribute

There are several ways to contribute beyond writing code:

- **Bug reports** — Open an issue with a clear reproduction case (see [Reporting Issues](#reporting-issues))
- **Feature requests** — Open an issue describing the problem you want solved, not the solution you have in mind
- **Documentation** — Fix a typo, clarify a step, add an example
- **Code** — Pick an item from the [Roadmap](README.md#roadmap--contributing) or fix a confirmed bug

---

## Development Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/your-org/maintainer-burnout-guard.git
cd maintainer-burnout-guard

python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install boto3
```

### 2. Configure AWS credentials

```bash
aws configure
# Or use a named profile:
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
```

### 3. Provision SSM parameters

Follow the [Configuration section in the README](README.md#configuration) to set up the required SSM parameters pointing at test repositories.

### 4. Run a local test invocation

```bash
python - <<'EOF'
from lambda.handler import handler

class FakeContext:
    aws_request_id = "local-test"

handler({}, FakeContext())
EOF
```

This runs the full pipeline against real AWS services using your local credentials.

---

## Branch & Commit Conventions

### Branches

```
feat/short-description       New feature
fix/short-description        Bug fix
docs/short-description       Documentation only
chore/short-description      Tooling, deps, config
refactor/short-description   Code change with no behaviour change
```

### Commit messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <short imperative summary>

Optional longer body explaining the why, not the what.
```

**Types:** `feat`, `fix`, `docs`, `chore`, `refactor`, `test`

**Examples:**

```
feat: add per-repo lookback hour override via SSM

fix: handle None issue body from GitHub API gracefully

docs: add Slack delivery option to roadmap

chore: pin boto3 to 1.34.x in requirements-dev.txt
```

Keep the summary under 72 characters. Use the body for anything that needs context.

---

## Pull Request Process

1. **Fork** the repo and create your branch from `main`
2. **Make your changes** — one logical change per PR
3. **Test manually** by invoking the Lambda with a real EventBridge payload (`{}`)
4. **Update the README** if your change affects setup, configuration, or behaviour
5. **Open the PR** against `main` with:
   - A clear title following commit conventions
   - A description of what changed and why
   - Steps to verify the change (manual test instructions if applicable)

PRs will be reviewed within a few days. Small, focused PRs get reviewed faster.

### What makes a good PR

- Solves one thing
- Has no unrelated changes mixed in
- Leaves the codebase in a better state than it found it
- Doesn't introduce new dependencies without prior discussion

---

## Reporting Issues

Open an issue and include:

- **What you expected** to happen
- **What actually happened** (paste the CloudWatch log entry if applicable)
- **Steps to reproduce** — the Lambda payload, which SSM params were set, which region
- **AWS region** you're deploying in
- **SAM CLI version** (`sam --version`)

If the issue involves a credential or permission error, include the IAM action and resource from the error message — never paste your actual credentials or token values.

---

## What We Won't Accept

- PRs that add auto-posting to GitHub — the agent must remain draft-only
- New runtime dependencies that require a packaging step (keep it zero-dep)
- Changes that store secrets in environment variables or CloudFormation parameters
- Wildcard IAM permissions (`*` on actions or resources)
- PRs without a clear description of what problem they solve

---

Thank you for helping make open-source maintainership a little less exhausting.
