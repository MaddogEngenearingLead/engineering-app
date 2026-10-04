# Fresh Start: Clone/Setup and Run Tests

## Windows (Git Bash)

```bash
# Navigate to your project directory
cd engineering-app

# Pull latest changes from remote
git pull origin master

# Create a fresh virtual environment
python -m venv .venv

# Activate the virtual environment (Git Bash syntax)
source .venv/Scripts/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install all dependencies (including pytest)
pip install -r requirements.txt

# Run tests
python -m pytest tests -q

# View test results
echo "Tests completed!"
```

## Windows (Command Prompt / PowerShell)

```cmd
REM Navigate to your project directory
cd engineering-app

REM Pull latest changes from remote
git pull origin master

REM Create a fresh virtual environment
python -m venv .venv

REM Activate the virtual environment (CMD syntax)
.venv\Scripts\activate

REM Upgrade pip
python -m pip install --upgrade pip

REM Install all dependencies (including pytest)
pip install -r requirements.txt

REM Run tests
python -m pytest tests -q

REM View test results
echo Tests completed!
```

## macOS / Linux (Bash)

```bash
# Navigate to your project directory
cd engineering-app

# Pull latest changes from remote
git pull origin master

# Create a fresh virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install all dependencies (including pytest)
pip install -r requirements.txt

# Run tests
python -m pytest tests -q

# View test results
echo "Tests completed!"
```

---

## Quick Checklist

- [ ] Navigated to project directory
- [ ] Ran `git pull origin master` to get latest changes
- [ ] Created `.venv` virtual environment
- [ ] Activated virtual environment
- [ ] Upgraded pip
- [ ] Ran `pip install -r requirements.txt`
- [ ] Ran `python -m pytest tests -q`
- [ ] Tests passed or identified issues

---

## Common Issues & Fixes

### Issue: "No module named pytest"
**Solution:** Make sure you activated the virtual environment and ran `pip install -r requirements.txt`

```bash
# Verify activation (prompt should show (.venv))
source .venv/Scripts/activate  # Git Bash
# or
.venv\Scripts\activate  # CMD

# Reinstall requirements
pip install -r requirements.txt
```

### Issue: "git pull" shows conflicts
**Solution:** Stash local changes and pull latest

```bash
git stash
git pull origin master
git stash pop  # Optional: reapply your changes
```

### Issue: Virtual environment already exists
**Solution:** Remove old venv and create fresh one

```bash
# Git Bash or Linux/macOS
rm -rf .venv

# Windows CMD
rmdir /s /q .venv

# Then create new venv
python -m venv .venv
```

### Issue: Wrong Python version
**Solution:** Check Python version

```bash
python --version  # Should be 3.10 or newer (3.12 recommended)

# If wrong version, use full path
/usr/bin/python3.12 -m venv .venv  # Linux/macOS
C:\Python312\python.exe -m venv .venv  # Windows
```

---

## Verify Installation Success

After setup, run these commands to verify everything works:

```bash
# Test backend imports
python -c "from app.main import app; print('✅ Backend imports OK')"

# Test config loads
python -c "from app.config import settings; print(f'✅ Config loaded: {settings.app_name}')"

# Test health endpoint (start server in background, then curl)
# In one terminal:
uvicorn app.main:app --reload

# In another terminal:
curl http://localhost:8000/api/health
# Expected response: {"status":"ok","service":"engineering-app","environment":"development"}
```

---

## Next Steps After Tests Pass

1. ✅ Backend API startup validation
2. ✅ Frontend connection testing
3. ✅ API smoke tests
4. ✅ Phase 1 completion validation
