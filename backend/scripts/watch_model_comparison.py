"""Copy private comparison checkpoints from the VM and refresh local review sheets.

No generation calls or bank writes. Disconnects leave the VM job and saved
questions intact. Stop with Ctrl+C; rerun the same command to resume copying.
"""
import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="SSH user@host")
    parser.add_argument("--key", required=True, help="Existing private-key file path; never the key contents")
    parser.add_argument("--run", default="quality-20")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run):
        parser.error("Invalid run name")
    if args.host.startswith("-"):
        parser.error("Invalid host")
    root = Path(__file__).resolve().parents[2]
    folder = root / "tmp/verification/model-comparison"
    folder.mkdir(parents=True, exist_ok=True)
    ssh = shutil.which("ssh")
    node = shutil.which("node")
    if not ssh or not node:
        parser.error("SSH and Node must be available")
    command = [ssh, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-i", args.key,
               args.host, f"cat /home/ubuntu/Boom/backend/data/model_evaluations/{args.run}/state.json"]
    previous = None
    errors = 0
    while True:
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=35)
            result.check_returncode()
            state = json.loads(result.stdout)
            models = state["models"]
            progress = {k: {"model": v["model"], "saved": len(v["questions"]), "status": v["status"],
                            "last_error_code": v.get("last_error_code", ""), "retry_at": v.get("retry_at", 0)}
                        for k, v in models.items()}
            checkpoint = folder / "state.json"
            temporary = checkpoint.with_suffix(".tmp")
            temporary.write_text(result.stdout, encoding="utf-8")
            temporary.replace(checkpoint)
            signature = json.dumps(progress, sort_keys=True)
            if signature != previous:
                exported = subprocess.run([node, "scripts/export-model-comparison.mjs", str(checkpoint), str(folder / "review")],
                    cwd=root / "frontend", capture_output=True, text=True, encoding="utf-8", timeout=60)
                (folder / "export.log").write_text(exported.stdout + exported.stderr, encoding="utf-8")
                exported.check_returncode()
                (folder / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
                print(signature, flush=True)
                previous = signature
            errors = 0
            if args.once or (len(models) == 2 and all(len(v["questions"]) == 20 and v["status"] == "complete" for v in models.values())):
                return
            if any(v["status"].startswith("needs_attention") for v in models.values()):
                print("Saved samples exported; generator requires attention. No samples deleted.", flush=True)
                return
        except (subprocess.SubprocessError, OSError, ValueError, KeyError):
            errors += 1
            if errors >= 3 or args.once:
                print("Copying paused. VM generation and existing review sheets are preserved; rerun to resume.", flush=True)
                return
        time.sleep(max(30, min(args.interval, 60)))


if __name__ == "__main__":
    main()
