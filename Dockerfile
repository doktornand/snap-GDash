# ──────────────────────────────────────────────
# GDash — Globe Dashboard Backend FastAPI
# Compatible Python 3.8 · SnapDeploy ready
# ──────────────────────────────────────────────

FROM python:3.8-slim

# Métadonnées
LABEL maintainer="GDash"
LABEL description="Globe Dashboard API — météo, vols, séismes, espace, crypto et plus"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Répertoire de travail
WORKDIR /app

# Dépendances système (feedparser peut nécessiter des libs XML)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
 && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python en premier
# (couche Docker mise en cache si requirements.txt ne change pas)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Renommer le fichier principal pour que FastAPI/uvicorn le trouve
RUN if [ ! -f main.py ] && [ -f main_py38.py ]; then cp main_py38.py main.py; fi

# Exposition du port
EXPOSE 8000

# Healthcheck : vérifie que l'API répond
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Lancement avec uvicorn
# --host 0.0.0.0 obligatoire pour être accessible depuis l'extérieur du container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
