# The Azure VM

One VM, `swara-vm` in resource group `rg-swara` (Central India), runs the
whole stack with Docker Compose behind Caddy. It is a staging server. HTTPS is
open to everyone and the app's own sign-in protects accounts, because the
team's internet providers rotate their IP addresses too often for an
allowlist. SSH is closed to the internet: maintenance goes through
`az vm run-command`, which needs no open port. Students, who may be minors,
are not to use it before the legal review and guardian consent CLAUDE.md
requires.

| | |
| --- | --- |
| Address | `https://swara.dpdns.org`. The Azure name, `swara-reader-9259.centralindia.cloudapp.azure.com`, redirects there |
| Size | Standard_E4s_v5: 4 vCPU, 32 GB, 128 GB SSD. A free-trial subscription allows 4 vCPUs and no GPU |
| Power | Service hours, 06:00 to 23:00 Sri Lanka time, to make the credit last: $0.26 an hour, so about $133 a month rather than $187 for all day, before the disk. Azure's schedule shuts it down at 23:00; [`azure-vm-hours.yml`](../../.github/workflows/azure-vm-hours.yml) starts it at 06:00 and checks the site answers. Every container restarts unless stopped, so the stack comes back with the VM. Start it out of hours with `az vm start -g rg-swara -n swara-vm` |
| Checkout | `~/swara`, detached at the commit last deployed |
| Secrets | `~/swara/.env` (`SINHALA_READER_SECRET`), made on the VM, never committed |
| Settings | `~/deploy.env`, read by `deploy.sh`: `SINHALA_READER_TTS_PRECISION=fp32`, because a half-precision model on CPU fails to compute its speaker conditioning |
| Voice | The GPU voice on Modal (`SINHALA_READER_TTS=modal` in `~/deploy.env`; endpoint and key in `~/swara/.env`). The VM itself holds no model in memory. `~/models/xtts_si_female/` still has the five files, so removing that line from `~/deploy.env` and redeploying switches back to the local CPU voice |
| TLS | Caddy, a separate container, with a Let's Encrypt certificate. Port 80 is open to all for certificate renewal and redirects to HTTPS |
| History | `~/deployments.log`: every deploy's commit, voice, model checksum and image IDs |

## Continuous deployment

[`.github/workflows/deploy-azure.yml`](../../.github/workflows/deploy-azure.yml)
deploys every commit that passes CI on `main`. It can also be started by hand
from the Actions tab, on `main` only.

1. It signs in to Azure with GitHub's OIDC token. No password or key is
   stored. The identity `swara-github-deploy` has one role, "Swara VM
   deployer", on `rg-swara` only: read, start, stop and run commands on its
   VMs. Azure accepts the token only from this repository's `azure-staging`
   environment, and only `main` may deploy to that environment.
2. It starts the VM if the nightly shutdown stopped it.
3. Through `az vm run-command` it runs [`deploy.sh`](deploy.sh) *from the
   commit being deployed*. That script checks out the commit and builds the
   images. It starts the database and queue and waits for them, replaces the
   app's containers, and smoke-tests the API, readiness and the web app from
   inside the VM. If anything fails it prints the containers' states and the
   API's and web app's last log lines, then redeploys the previous commit.
4. It succeeds only if the script's last word is `DEPLOYED <sha>`. If it found
   the VM off, it leaves it on within service hours and turns it off outside
   them.

Deploys never overlap. A deploy that starts while one is running waits for it.

## By hand

```bash
az vm run-command invoke -g rg-swara -n swara-vm --command-id RunShellScript \
  --scripts "cd /home/azureuser/swara && sudo -u azureuser -H git fetch -q origin && sudo -u azureuser -H git show <sha>:infra/azure/deploy.sh > /tmp/d.sh && sudo -u azureuser -H bash /tmp/d.sh <sha>"
```

To roll back, deploy an earlier commit the same way; `~/deployments.log`
lists them.

## Not yet in place

- Images are built on the VM from the commit rather than in CI and pulled by
  digest, so a rebuild can pick up a newer base image. Pushing immutable
  images to a registry is the next step for a production server.
- There is no production environment, and so no approval gate. A production
  deploy must use a protected environment with a required reviewer, as
  CLAUDE.md requires.
- The deploy's smoke test runs inside the VM. The public address is checked
  from outside only once a day, by the morning start, and nothing alerts
  anyone during the day if the site goes down.
