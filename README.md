# 🛡️ Maintainer Burnout Guard

> A serverless AI agent that triages toxic and low-effort GitHub issues overnight — so maintainers wake up to context and copy-ready responses, not raw noise.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-FF9900?logo=awslambda&logoColor=white)
![Amazon Bedrock](https://img.shields.io/badge/Amazon-Bedrock%20Nova%20Lite-232F3E?logo=amazonaws&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![IaC](https://img.shields.io/badge/IaC-AWS%20SAM-FF9900?logo=amazonaws&logoColor=white)

---

## About the Project

Open-source maintainers burn out. A significant driver is the daily grind of responding to issues that are vague, entitled, or outright hostile — each one a small but compounding tax on focus and mental health.

**Maintainer Burnout Guard** is a fully serverless AWS agent that runs every night without intervention. It fetches newly opened GitHub issues, sends each one to **Amazon Bedrock (Nova Lite)** for AI analysis, flags problematic submissions by severity, drafts a tailored empathetic response for each, and delivers a clean HTML digest to your inbox every morning.

You review the drafts, copy the ones you like, and post them. The agent never touches GitHub directly.

---

## Key Features

- **Autonomous nightly triage** — EventBridge fires the agent on a cron schedule; zero manual steps
- **AI-powered issue scoring** — Bedrock evaluates sentiment, entitlement tone, and clarity for every issue in parallel
- **Severity-aware response drafting** — three distinct prompt strategies: missing info (SEV-1), dismissive tone (SEV-2), CoC violations (SEV-3)
- **Human-sounding drafts** — responses never mention AI; written to sound like the maintainer authored them
- **Polished HTML digest** — colour-coded severity badges, direct GitHub links, and copy-ready reply blocks
- **Zero dependencies** — uses Python stdlib + boto3 (pre-installed in Lambda); no packaging step needed
- **Least-privilege IAM** — SSM, Bedrock, and SES permissions are individually scoped; no wildcard actions
- **Graceful degradation** — a single failed Bedrock call never crashes the run; errors are logged and skipped

---

## Tech Stack & Architecture

| Layer | Service |
|---|---|
| Scheduler | Amazon EventBridge (cron) |
| Compute | AWS Lambda (Python 3.12) |
| AI Analysis & Drafting | Amazon Bedrock — Nova Lite (`amazon.nova-lite-v1:0`) |
| Email delivery | Amazon SES |
| Configuration & Secrets | AWS SSM Parameter Store (SecureString) |
| Observability | Amazon CloudWatch Logs (structured JSON) |
| Infrastructure as Code | AWS SAM (`infra/template.yaml`) |

### Pipeline

```
EventBridge cron(0 7 * * ? *)
    │
    ▼
Lambda: handler.handler
    │
    ├─ 1. load_config()       SSM batch GetParameters
    ├─ 2. fetch_issues()      GitHub REST API, paginated, per repo
    ├─ 3. analyze_all()       Bedrock Converse — parallel (ThreadPoolExecutor x10)
    │       └─ sentiment / tone / clarity → flagged + severity 1–3
    ├─ 4. draft_response()    Bedrock Converse — sequential, flagged only
    │       └─ severity-specific prompt → empathetic plain-text reply
    ├─ 5. build_digest()      HTML + plain-text email body
    └─ 6. send_digest()       SES SendEmail → maintainer inbox
```

### Project Structure

```
maintainer-burnout-guard/
├── lambda/
│   ├── __init__.py
│   ├── handler.py              # Entry point + orchestration
│   ├── config.py               # SSM loader, AppConfig dataclass
│   ├── github/
│   │   ├── __init__.py
│   │   └── fetch_issues.py     # GitHub REST client (stdlib urllib)
│   ├── analysis/
│   │   ├── __init__.py
│   │   └── analyze_issue.py    # Bedrock analysis — structured JSON output
│   ├── response/
│   │   ├── __init__.py
│   │   └── draft_response.py   # Bedrock response drafting
│   ├── digest/
│   │   ├── __init__.py
│   │   └── build_digest.py     # HTML + plain-text digest builder
│   └── email/
│       ├── __init__.py
│       └── send_digest.py      # SES delivery
├── infra/
│   └── template.yaml           # AWS SAM — all infra as code
├── .env.example                # SSM parameter reference (not used at runtime)
└── README.md
```

---

## Getting Started

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) | v2 | Configured with deploy permissions |
| [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) | Latest | For build and deploy |
| AWS Account | — | With access to Lambda, IAM, EventBridge, SES, Bedrock, SSM |

No local Python environment needed — Lambda runs Python 3.12 in the cloud and boto3 is pre-installed.

---

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/i_arshii/maintainer-burnout-guard.git
cd maintainer-burnout-guard

# 2. Build the SAM package
sam build --template infra/template.yaml

# 3. Deploy (interactive first-time setup)
sam deploy --guided
```

During `--guided` you will be prompted for:
- **Stack name** — e.g. `maintainer-burnout-guard`
- **AWS Region** — must match where you verified SES and enabled Bedrock
- **Confirm IAM role creation** — enter `y`

Subsequent deploys:

```bash
sam deploy
```

---

### Configuration

All runtime config is stored in **AWS SSM Parameter Store** — nothing in environment variables, nothing in code.

#### Step 1 — Enable Amazon Nova Lite in Bedrock

1. Open the [Bedrock console](https://console.aws.amazon.com/bedrock) → **Model access**
2. Find **Amazon Nova Lite** → click **Request access**
3. Wait for **Access granted** (typically instant)

#### Step 2 — Verify your SES sender identity

```bash
aws ses verify-email-identity --email-address guard@yourdomain.com
```

Click the verification link in your inbox. If your account is in **SES sandbox**, also verify the recipient address, or [request production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html).

#### Step 3 — Create a GitHub Personal Access Token

Go to [github.com/settings/tokens](https://github.com/settings/tokens) and generate a **classic token** with `repo` scope (read-only is sufficient).

#### Step 4 — Provision SSM parameters

```bash
# GitHub token — stored as SecureString (KMS-encrypted)
aws ssm put-parameter \
  --name "/burnout-guard/github-token" \
  --value "ghp_your_token_here" \
  --type SecureString

# Repositories to monitor (comma-separated)
aws ssm put-parameter \
  --name "/burnout-guard/repos" \
  --value "owner/repo1,owner/repo2" \
  --type String

# SES sender (must be verified)
aws ssm put-parameter \
  --name "/burnout-guard/ses-from" \
  --value "guard@yourdomain.com" \
  --type String

# Digest recipient
aws ssm put-parameter \
  --name "/burnout-guard/ses-to" \
  --value "you@yourdomain.com" \
  --type String

# Lookback window in hours (how far back to scan on each run)
aws ssm put-parameter \
  --name "/burnout-guard/lookback-hours" \
  --value "24" \
  --type String

# Bedrock model ID
aws ssm put-parameter \
  --name "/burnout-guard/bedrock-model-id" \
  --value "amazon.nova-lite-v1:0" \
  --type String
```

All parameter paths are documented in [`.env.example`](.env.example).

---

## Usage

### Trigger a manual run

After deploying, test the full pipeline immediately from the AWS console:

1. Open **Lambda** → `maintainer-burnout-guard` → **Test** tab
2. Create a test event with payload `{}`
3. Click **Test** — you should receive a digest email within ~30 seconds

Or via CLI:

```bash
aws lambda invoke \
  --function-name maintainer-burnout-guard \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  response.json && cat response.json
```

### Adjust the schedule

The default schedule is **07:00 UTC daily**. Override at deploy time:

```bash
# Run at 06:00 UTC instead
sam deploy --parameter-overrides CronSchedule="cron(0 6 * * ? *)"
```

### View execution logs

```bash
# Tail live logs
aws logs tail /aws/lambda/maintainer-burnout-guard --follow

# Filter for flagged issue counts only
aws logs filter-log-events \
  --log-group-name /aws/lambda/maintainer-burnout-guard \
  --filter-pattern '"step":"complete"'
```

Every pipeline step emits a structured JSON log entry:

```json
{ "step": "analyze_all", "detail": "reviewed=12 flagged=3", "elapsed_ms": 4821.3 }
{ "step": "complete", "request_id": "abc-123", "total_ms": 9203.1, "reviewed": 12, "flagged": 3 }
```

---

## Severity Reference

| Level | Trigger | Draft strategy |
|---|---|---|
| **SEV-1** | Missing reproduction steps, version info, or vague description | Warmly asks for the specific missing details |
| **SEV-2** | Dismissive, entitled, or condescending tone toward maintainers | Reframes as collaboration without lecturing |
| **SEV-3** | Aggressive, threatening, or Code of Conduct–violating language | Acknowledges briefly, references CoC, invites re-engagement |

---

## Cost Estimate

At typical open-source scale (≤ 50 issues/day, running once daily):

| Service | Est. monthly cost |
|---|---|
| Lambda (1 invocation/day × 300s × 256 MB) | ~$0.00 (free tier) |
| Bedrock Nova Lite (~100 Converse calls/day) | ~$0.10 – $0.30 |
| SES (30 emails/month) | ~$0.00 (first 62k free) |
| SSM standard parameters | ~$0.00 (free) |
| EventBridge scheduled rule | ~$0.00 |
| **Total** | **< $0.50 / month** |

---

## Roadmap & Contributing

Planned for future releases:

- [ ] Multi-recipient digest support
- [ ] Per-repo configuration overrides
- [ ] Slack/Teams digest delivery option
- [ ] Weekly summary report (trends over time)
- [ ] GitHub App integration for one-click reply posting

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

```bash
# Fork → clone → branch
git checkout -b feat/your-feature

# Make changes, then open a PR against main
```

---

## License & Acknowledgments

Released under the [MIT License](LICENSE).

Built with:
- [AWS Serverless Application Model (SAM)](https://aws.amazon.com/serverless/sam/)
- [Amazon Bedrock — Nova Lite](https://aws.amazon.com/bedrock/nova/)
- [GitHub REST API](https://docs.github.com/en/rest)
