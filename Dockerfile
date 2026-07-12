FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py query.py ./

# Cloud Run sets $PORT at runtime; default to 8080 for local docker run
ENV PORT=8080

EXPOSE 8080

# --server.address=0.0.0.0 required — Cloud Run only accepts traffic on 0.0.0.0
# --server.headless=true    disables the "open browser" prompt
# --server.enableCORS=false safe behind Cloud Run's managed ingress
CMD streamlit run app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false
