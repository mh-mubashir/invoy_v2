# Push Invoy SDK to GitHub

Your project is ready to push. Git is initialized, `.gitignore` is configured, and the initial commit is done.

## 1. Create the repository on GitHub

1. Go to [https://github.com/new](https://github.com/new)
2. Choose a name (e.g. `invoy-sdk` or `invoy_v2`)
3. Set visibility (Public or Private)
4. **Do not** initialize with README, .gitignore, or license (we already have these)
5. Click **Create repository**

## 2. Add remote and push

After creating the repo, GitHub shows you the repository URL. Use one of these:

**HTTPS** (simplest; will prompt for credentials):

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

**SSH** (if you use SSH keys with GitHub):

```bash
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

Replace `YOUR_USERNAME` and `YOUR_REPO_NAME` with your GitHub username and repo name.

## 3. Set up on another machine

Once pushed, on your other machine:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git invoy_v2
cd invoy_v2
pip install -e .
```

Then run the activity example:

```bash
ollama pull llava   # one-time: get the vision model
python example_activity.py
```

The `activity_log.db` and `screenshots/` folder will be created automatically on first run.

## Git identity (optional)

To set your name and email for future commits:

```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```
