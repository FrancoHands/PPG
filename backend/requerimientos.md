RSS Requerimientos

Base
Crear una aplicación web local independiente que corra de manera autónoma y sincrónica
de los servidores remotos, la aplicación debe poder funcionar localmente sin depender continuamente de servidores externos. Especializada para proyectos (ej: reactores nucleares) en la creación y
edición de procedimientos que conllevan tareas, que a su vez conllevan pasos, los cuales son
interpretados cómo acciones. Su función principal es la validación en tiempo real de estas tareas. La
aplicación estará formada de forma matricial, donde cada uno de los módulos estarán conectados
para el traslado de información.

-------------------------------------------------------------------

Backend (basado en FastAPI)
Clasificación:
Separa en clases que no heredan (son independientes) pero que tienen la siguiente jerarquía:
- Procedimiento {id, nombre, información, validación}
    - Tareas {id, nombre, información, validación, orden}
        - Pasos {id, nombre, información, validación, orden}
            - Acciones {id, nombre, información, tipo, parámetros}
            - Objetos {id, nombre, información}
            - Acciones {id, nombre, información, tipo, parámetros}
            - Condiciones {id, nombre, información}
            - Locations {id, nombre, información}
            - Estados {id, nombre, información}
            - Cualquier tipo que pueda ser agregado en el futuro (es editable)


A su vez, con los métodos HTTP: GET, POST, DELETE y PUT se creará un apartado donde se
agregarán, modificarán y eliminarán cada una de estas clases. A su vez, se podrá clonar los
procedimientos para reutilizarlos en otro proyecto para facilitar la creación de los mismos. Todas
estas tareas pasos y acciones estarán almacenadas en 2 bases de datos que estarán conectadas al
backend, dentro del backend se crearan todas la información requerida dentro de los procedimientos desde 0.

-------------------------------------------------------------------

Base de datos PogresSQL
Esta se utilizará para almacenar de manera asincrónica la información de las tareas, procedimientos y pasos (la cantidad
puede variar según el procedimiento: ~100) junto con su nombre, id e información. La información será devuelta en formato JSON al frontend cuando sea requerida.

-------------------------------------------------------------------
Base de datos Neo4j
Esta se utilizará para almacenar dentro de un servidor nodos cada una de las acciones, objetos, locations y demás dentro de pasos, no
tendrán relaciones entre sí, cada una será dependiente únicamente por la tarea realizada. La información será devuelta en formato JSON al frontend cuando sea requerida.

-------------------------------------------------------------------

Frontend (basado en React)
Este tendrá una pantalla de inicio donde se podrá seleccionar distintas funciones dentro de la app:
- Un apartado para inicializar los procedimientos ya guardados en la base de datos, dentro se
podrá ver en formato de grilla las tareas a completar en órden cronológico, señalizando con hora, minuto y segundo el momento en el que fueron realizadas. Cada una contará con un indicador,
verde para ‘completada’, amarillo para ‘en proceso’, gris para ‘pendiente’ y rojo para ‘error’.
- Otro apartado para la creación edición de procedimientos y tareas
- Otro apartado para el clonado de un procedimiento.

-------------------------------------------------------------------

Requisitos pendientes de instalación / configuración

1) Para crear el Frontend y conectarlo con React
- Node.js (LTS) y npm instalados en el sistema.
- Crear el proyecto con Vite: `npm create vite@latest frontend -- --template react` (usar `react-ts` si se decide usar TypeScript).
- Librerías a instalar dentro de la carpeta `frontend/`:
    - `axios` (o usar `fetch` nativo) para consumir la API del backend.
    - `react-router-dom` para navegar entre los apartados (inicio, procedimientos, creación/edición, clonado).
    - `@tanstack/react-query` o `zustand` para el manejo de estado y caché de los datos remotos (opcional, recomendado).
- En el Backend (FastAPI), agregar a `main.py` el middleware `CORSMiddleware` (de `fastapi.middleware.cors`) para permitir las peticiones desde el origen del frontend (ej: `http://localhost:5173`), ya que actualmente no está configurado.
- Definir en el frontend la URL base de la API mediante variable de entorno (ej: `VITE_API_URL=http://localhost:8000`).

2) Para cuando PostgreSQL ya esté instalado
- Agregar el driver de conexión a `requirements.txt`: `psycopg2-binary` (driver síncrono, compatible con SQLAlchemy tal como ya está usado en `database.py`).
- Definir la variable de entorno `DATABASE_URL` con el formato `postgresql://usuario:clave@host:5432/nombre_basededatos`.
- Crear previamente en PostgreSQL la base de datos y el usuario indicados en `DATABASE_URL` (no se crean automáticamente).
- No se requieren cambios adicionales en `database.py`: `init_db()` ya crea las tablas con `metadata.create_all(engine)` sin importar el motor de base de datos.
- (Opcional) `alembic` si se prefiere manejar migraciones versionadas en lugar de `create_all`.

-------------------------------------------------------------------

Inventario de lo instalado actualmente (para futura migración a otra PC)

Sistema (global, fuera del proyecto):
- Python 3.14.6, instalado en `C:\Users\Prestamo\AppData\Local\Python\pythoncore-3.14-64` (Python Install Manager de python.org). También existe el alias `python.exe` de Microsoft Store en `AppData\Local\Microsoft\WindowsApps`.
- Docker (Desktop/Engine) 29.5.3, build d1c06ef.
- NO instalados globalmente todavía: Node.js/npm, Git, PostgreSQL (cliente `psql`), Neo4j.

Entorno virtual del proyecto (`.venv/`, Python 3.14.6) — el que usa realmente el backend, instalado con `pip install -r backend/requirements.txt`:
- fastapi 0.138.0
- pydantic 2.13.4
- SQLAlchemy 2.0.51
- uvicorn 0.49.0
- Dependencias transitivas: starlette, anyio, h11, click, colorama, greenlet, pydantic_core, typing_extensions, typing-inspection, annotated-types, annotated-doc, idna.

Nota: en la raíz del proyecto también existe una carpeta `venv/` que está vacía (solo tiene `pip`); no se usa y no debe migrarse ni confundirse con `.venv/`.

Docker:
- `backend/Dockerfile`: imagen base `python:3.12-slim`, instala `backend/requirements.txt`, expone el puerto 8110.
- `docker-compose.yml` (raíz): levanta el servicio `backend`, mapea el puerto 8110 y monta `backend/data.db` y `backend/exports/` como volúmenes.

Base de datos actual: SQLite (`backend/data.db`). Aún no hay PostgreSQL ni Neo4j instalados (ver requisitos pendientes más arriba).

Pasos para migrar el proyecto a otra computadora (con permisos de administrador):
1. Instalar Python 3.14 (misma versión usada) y Docker Desktop.
2. Copiar el código del proyecto, evitando copiar las carpetas `venv/`, `.venv/`, `__pycache__/` y los archivos `*.log`/`*.pid` (son artefactos locales, no código).
3. Recrear el entorno virtual en la PC nueva: `python -m venv .venv` y luego `pip install -r backend/requirements.txt` (nunca copiar la carpeta `.venv/` entre máquinas, no es portable).
4. Si se prefiere usar Docker en lugar de instalar Python manualmente, basta con correr `docker compose up --build` desde la raíz del proyecto.