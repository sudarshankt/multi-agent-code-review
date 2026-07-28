# eval_harness — standalone benchmark harness, Streamlit GUI.
# Build context MUST be the repo root (not this directory) so
# requirements.txt's `-e ../..` resolves to the real root project.
FROM python:3.12-slim

# The dataset downloaders (download_seccodeplt/bugsinpy/patcheval.py) shell
# out to `git clone` directly — without this, "Download missing datasets"
# in the GUI fails silently on a fresh image with no eval/data/ yet.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

WORKDIR /app/eval_harness/eval_harness

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8502

CMD ["python", "-m", "streamlit", "run", "gui/app.py", "--server.address", "0.0.0.0", "--server.port", "8502"]
