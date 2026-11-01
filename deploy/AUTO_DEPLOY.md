# Oracle automatic deployment

The VM polls public `ImasraI/Boom` main every two minutes, after boot as well.
No inbound webhook, laptop/VPN availability, GitHub secret or SSH key in GitHub
is required. Cloudflare continues its existing Git-connected frontend deployment.

The updater fetches without changing the running checkout, then waits for the
latest **Boom checks** push workflow for that exact main SHA to finish successfully.
Failed/pending/missing checks, GitHub/network errors, local checkout changes,
unexpected remotes and unexpected branches all hold deployment. It fast-forwards
only; no force push or overwritten local edits. Concurrent invocations are locked.

Backend code/dependency changes stop the single API writer, back up SQLite using
its backup API and copy stopped Chroma plus the private environment, then update,
install changed production requirements and restart. Secrets/uploads/vectors and
the current production policy setting remain intact. `/api/health` must return
200 with status=ok. Failure rolls CODE back to the preceding revision, attempts
to restore prior requirements and restart, and quarantines the failed SHA until
a newer tested commit exists. It never restores old account/corpus databases
automatically, because that could erase post-deploy writes. Destructive schema or
environment changes still require a maintenance deployment and explicit review.

Frontend/docs/tools-only changes update the VM checkout without an API restart.
Backups are kept under `/home/ubuntu/backups/automatic/`; there is no automatic
deletion. Disk-space checks hold deployment before a new backend backup if space
is insufficient. A health endpoint cannot detect every functional regression;
CI and subsequent application smoke checks remain necessary.

Installed files:

- `/home/ubuntu/.local/lib/boom-deploy/auto_update.py`
- `/etc/systemd/system/boom-autodeploy.service`
- `/etc/systemd/system/boom-autodeploy.timer`
- State: `/home/ubuntu/.local/state/boom-deploy/status.json`

Read status/logs on the VM:

```bash
systemctl list-timers boom-autodeploy.timer
cat /home/ubuntu/.local/state/boom-deploy/status.json
journalctl -u boom-autodeploy.service -n 60 --no-pager
```

Pause/resume safely (a running deployment finishes its current transaction):

```bash
touch /home/ubuntu/.local/state/boom-deploy/PAUSED
sudo systemctl stop boom-autodeploy.timer
# Resume:
rm /home/ubuntu/.local/state/boom-deploy/PAUSED
sudo systemctl start boom-autodeploy.timer
```

The installed updater and service units are deliberately not self-replaced by a
repository update. Changes to deployment machinery itself require a reviewed
installation. Normal application pushes need no manual SSH pull/restart.

CI prerequisites for the new authoring tests include frontend npm dependencies,
jsonschema and a scratch-directory creation on clean runners. Local pre-existing
directories/packages must not hide missing clean-runner setup.
