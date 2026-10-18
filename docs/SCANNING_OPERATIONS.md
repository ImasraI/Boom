# Local scanning: running and monitoring

The scanner is a normal Python program; no AI agent is needed to operate it.
The laptop must remain awake. Closing its scanner terminal ends the process;
sleep, shutdown and reboot stop computation. Restarting resumes saved work.

## Commands from any PowerShell directory

```powershell
# Resume saved work, then automatically continue successive batches.
& 'C:\Users\Arsam\Desktop\Boom-merged\START-EXAM-WORKERS.cmd'

# Read status without starting scanning.
& 'C:\Users\Arsam\Desktop\Boom-merged\START-EXAM-WORKERS.cmd' status

# Start only the monitor.
& 'C:\Users\Arsam\Desktop\Boom-merged\START-EXAM-WORKERS.cmd' monitor

# Safe stop: stop dispatch, finish bounded active requests, then exit.
& 'C:\Users\Arsam\Desktop\Boom-merged\START-EXAM-WORKERS.cmd' stop

# Select the next 30 pages, only after the saved batch is complete.
& 'C:\Users\Arsam\Desktop\Boom-merged\START-EXAM-WORKERS.cmd' next

# Explicit proxy change; running workers reload after requests drain.
& 'C:\Users\Arsam\Desktop\Boom-merged\START-EXAM-WORKERS.cmd' proxy http://127.0.0.1:10809
```

In Command Prompt omit the initial `&` and use double quotes around the path.
`proxy auto` pins the documented local VPN endpoint 10809 even when offline;
`proxy direct` explicitly opts into direct connections. Proxy URLs cannot
contain credentials. Settings persist in ignored
`backend/data/exam_examples/scanner-settings.json`. Changing a parent shell's
environment does not update an already running process; use the proxy command.

## Dashboard

Open http://127.0.0.1:8770/ after starting the monitor. It reads local files and
does not call providers. It shows phase, process/heartbeat status, last saved
page, selected batch offset, active requests, pending pages and per-key cooldowns.
Labels are anonymous; raw credentials are never served.

- `scanning`: requests or page processing are active.
- `waiting for network`: configured proxy is unavailable; it checks every five
  seconds without provider requests. Restore the proxy or explicitly change it.
- `waiting for saved provider retry`: honor the recorded provider deadline.
  Network restoration does not erase daily quotas or authentication failures.
- `stopping`: wait for active requests to drain; do not close the terminal yet.
- `benchmark complete`: this selected batch ended. It does not automatically
  advance unless launched with automatic continuation. The normal launcher now
  enables automatic continuation; restart it to resume and advance.
- `stopped`: resume with the ordinary launcher.
- `unresponsive`: PID exists but heartbeat is older than 90 seconds. Inspect
  the terminal. The launcher avoids starting a competing coordinator.

The request client is recreated for each request. Connection establishment and
pool waits time out after 10 seconds; writes after 60; response inactivity after
300. Network failures preserve the page queue and do not consume document-quality
retries. Restoring connectivity allows automatic retry after the saved transport
cooldown (typically 30 seconds). These are inactivity limits, not a promise that
every page finishes within a fixed wall time. Other provider cooldowns can last
longer. A listening proxy alone does not prove access to an AI provider.

## What the counts mean

One coordinator dispatches up to 30 tasks; the current Gemini profile has 13
unique Gemini credentials, so 30 slots do not mean 30 simultaneous Gemini calls.
Credential selection respects independent saved cooldowns and availability.

Selected pages are the current bounded batch. Requests include failures/retries.
Saved OCR candidates passed format checks; covers may have no questions. Held
pages exhausted quality retries and need inspection. Retained candidates include
older profiles, so their total differs from the current batch. Source-checked
pages and human/scientific review are separate evidence levels. A valid JSON
response is never proof that its equations, diagrams or text match the source.

Checkpoints live under `backend/data/exam_examples/documents/<hash>/vision/`.
`scan-status.json` and `coordinator-status.json` describe liveness/progress;
`vision-quota.json` and `vision-service-health.json` preserve provider refusals.
Never delete those files to force retries. The OS worker lock prevents duplicate
writers and is released on process exit/crash; a stale PID file is not the lock.

The normal launcher enables continuous candidate scanning with `--auto-next`: it
advances only completed batches, stops at the end of selected sources, and never
auto-approves OCR. For a single batch, invoke the Python CLI without `--auto-next`.
No Windows service, startup task or generic crash-restart loop is installed. Unexpected programming failures should be diagnosed,
not hidden in endless restart loops. Use the launcher after reboot or a crash.


## Leaving the laptop running for a day

Plug it into power, leave the lid open, start the launcher and confirm a fresh
heartbeat in the dashboard. Keep the scanner terminal open. The coordinator
prevents idle system sleep while running (including quota/network waits) and
restores its previous execution-state requirement when it exits. The display can
turn off. Explicit sleep, lid-close actions, shutdown and Windows restarts still
interrupt work; restart the launcher afterwards.

Completed batches advance automatically without an agent. Network waits and
provider cooldowns do not skip pages. Held pages remain held for review rather
than being retried endlessly. A terminal credential refusal with no retry time
or an unexpected programming error can still require attention; unlimited
progress cannot be guaranteed by keeping the process alive.
