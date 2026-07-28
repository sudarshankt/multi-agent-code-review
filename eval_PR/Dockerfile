# eval_PR — standalone real-PR audit tool, Streamlit GUI
FROM python:3.12-slim

# The GUI's "Fetch PR/branch/commit from GitHub" buttons (fetch_pr_diff,
# fetch_branch_code, fetch_commit_code in gui/app.py) all shell out to the
# `gh` CLI — without it, every fetch button fails. gh auto-picks up
# GITHUB_TOKEN from the environment (already set via docker-compose's
# env_file), no separate `gh auth login` needed.
RUN apt-get update && apt-get install -y --no-install-recommends curl gpg \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY eval_PR/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY eval_PR/ ./

RUN pip install --no-cache-dir -e ".[gui]"

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "eval_pr/gui/app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
