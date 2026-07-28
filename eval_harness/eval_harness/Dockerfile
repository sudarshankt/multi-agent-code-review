# eval_harness — standalone benchmark harness, Streamlit GUI.
# Build context MUST be the repo root (not this directory) so
# requirements.txt's `-e ../..` resolves to the real root project.
FROM python:3.12-slim

WORKDIR /app

COPY . .

WORKDIR /app/eval_harness/eval_harness

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8502

CMD ["python", "-m", "streamlit", "run", "gui/app.py", "--server.address", "0.0.0.0", "--server.port", "8502"]
