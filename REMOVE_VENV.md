# Removing Virtual Environment

If you want to remove the virtual environment (`.venv` or `venv` folder) from your local machine, follow these steps:

### Windows (PowerShell)
```powershell
Remove-Item -Recurse -Force .venv
# Or if your folder is named 'venv'
Remove-Item -Recurse -Force venv
```

### Linux / macOS
```bash
rm -rf .venv
# Or if your folder is named 'venv'
rm -rf venv
```

**Note:** If you remove the virtual environment, you will need to reinstall all dependencies (e.g., `pip install -r requirements.txt`) before running the backend again if you choose to set up a new environment later.
