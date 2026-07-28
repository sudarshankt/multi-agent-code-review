# eval_PR — standalone real-PR audit tool, Streamlit GUI
FROM python:3.12-slim

WORKDIR /app

COPY eval_PR/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY eval_PR/ ./

RUN pip install --no-cache-dir -e ".[gui]"

EXPOSE 8501

CMD ["python", "-m", "streamlit", "run", "eval_pr/gui/app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
