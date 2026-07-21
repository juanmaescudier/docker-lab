# Dockerfile del servicio "api" (Flask)
# Objetivo (Definition of Done del M0): imagen ligera, multi-stage, usuario no-root

FROM python:3.13-slim

# Creación de un directorio de trabajo en Docker
WORKDIR /app

# Instalacion de dependencias (el punto nos indica WORKDIR /code) el copy tambien es de host:cont
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar de local al directorio del contenedor siempre de host:cont
COPY . .

# Exposición de un puerto
EXPOSE 8000

# Cambiar de usuario antes de ejecutar codigo (minimo privilegio)
RUN useradd -r -u 1001 appuser
USER appuser

# Ejecucion del codigo
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:app"]