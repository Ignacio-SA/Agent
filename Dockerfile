FROM python:3.12-slim

# Instalar dependencias del sistema + ODBC Driver 17 (requerido por pyodbc / MS Fabric)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        apt-transport-https \
        unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl https://packages.microsoft.com/config/debian/12/prod.list \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (capa cacheada)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
