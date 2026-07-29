# Dockerfile del worker
# Objetivo: imagen ligera, single-stage, usuario no-root

FROM python:3.13-slim

# Parchear el SO cuanto antes (capa estable, cacheable)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Creación de un directorio de trabajo en Docker
WORKDIR /worker

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar de local al directorio del contenedor siempre de host:cont
COPY . .

# Cambiar de usuario antes de ejecutar codigo (minimo privilegio)
RUN useradd -r -u 1001 appuser
USER appuser

# Ejecucion del codigo
CMD ["python", "worker.py"]