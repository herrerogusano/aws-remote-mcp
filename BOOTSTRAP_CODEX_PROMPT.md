# Initial prompt for Codex — Exercise 5

Quiero que prepares e inicies de forma autónoma el último proyecto de mi portfolio AWS: **Exercise 5 — AWS Remote MCP**.

## 1. Planning ZIP

En mi carpeta de Descargas existe:

`aws-remote-mcp-planning.zip`

Localízalo automáticamente en `Downloads` / `Descargas` del usuario.

No modifiques el ZIP original.

## 2. New repository

Crea un repositorio local independiente llamado:

`aws-remote-mcp`

Créalo en la misma ubicación general donde se encuentran mis otros repositorios AWS/portfolio si puedes inferirla de forma fiable.

Antes de crear nada, comprueba que no exista ya un repositorio con ese nombre. Nunca sobrescribas trabajo existente.

## 3. Extract planning into repository root

Extrae el ZIP y copia **su contenido**, no la carpeta contenedora, directamente a la raíz del nuevo repositorio.

El resultado debe empezar así:

```text
aws-remote-mcp/
├── AGENTS.md
├── PLAN.md
├── START_CODEX.md
├── BOOTSTRAP_CODEX_PROMPT.md
└── docs/
    └── plan/
        ├── GATES.md
        ├── PROGRESS.md
        ├── REFERENCES.md
        └── phases/
```

NO quiero:

```text
aws-remote-mcp/
└── aws-remote-mcp-planning/
```

`AGENTS.md` tiene que quedar en la raíz.

## 4. Read all planning

Lee completamente y en este orden:

1. `AGENTS.md`
2. `PLAN.md`
3. `START_CODEX.md`
4. `docs/plan/GATES.md`
5. `docs/plan/PROGRESS.md`
6. `docs/plan/REFERENCES.md`
7. todos los archivos de `docs/plan/phases/`

A partir de ahí considera esos archivos la fuente de verdad del ejercicio.

## 5. Previous repositories

Busca mis ejercicios AWS anteriores.

Especialmente:

`aws-resource-mcp`

que corresponde al Exercise 2.

Úsalo como referencia para patrones de inventario AWS, Boto3, normalización, guard de costes, consentimientos, contadores y errores parciales.

NO crees una dependencia runtime con ese repositorio.

## 6. Git and GitHub

Inicializa Git con `main` si es necesario.

Usa la autenticación GitHub ya disponible en mi entorno para crear el repositorio remoto:

`aws-remote-mcp`

Configura `origin` y publica el estado inicial cuando corresponda siguiendo `AGENTS.md`.

No crees tokens GitHub permanentes nuevos si ya existe autenticación válida.

## 7. Autonomous workflow

No te detengas después de crear el repositorio.

Empieza inmediatamente la primera fase pendiente de `docs/plan/PROGRESS.md`.

Salvo que `GATES.md` indique lo contrario, tienes autonomía para:

```text
leer fase
→ crear branch
→ implementar
→ ejecutar tests/checks
→ corregir errores
→ actualizar docs/PROGRESS
→ commit
→ push
→ PR
→ comprobar CI
→ corregir CI
→ merge si está verde
→ actualizar main local
→ siguiente fase
```

No me pidas permiso por las operaciones Git normales anteriores.

## 8. Critical gates

Respeta estrictamente `docs/plan/GATES.md`.

Cuando llegues a un gate:

1. prepara todo lo que puedas localmente;
2. ejecuta tests;
3. prepara IaC/diffs;
4. revisa IAM/auth/secrets;
5. verifica precios actuales en fuentes oficiales cuando aplique;
6. explica qué acción crítica quieres realizar;
7. DETENTE antes de realizarla.

En ese momento muestra:

```text
GATE: <nombre>

Fase actual:
...

Ya preparado:
...

Acción crítica:
...

Recursos afectados:
...

IAM/auth:
...

Secretos:
...

Coste/riesgo:
...

Qué ocurrirá si autorizo:
...

Rollback:
...
```

Espera mi autorización explícita.

## 9. Cost policy

Mantén la política:

**cero costes accidentales**.

Las operaciones seguras pueden automatizarse. Las operaciones potencialmente facturables, desconocidas, nuevos recursos persistentes o cambios relevantes de IAM deben respetar sus gates.

## 10. CI and CD

CI debe existir desde la Fase 0 e ir creciendo con el proyecto.

CD NO debe activarse hasta que el proceso de deployment manual sea estable y la fase correspondiente lo indique.

Cuando CD esté activo, recuerda que hacer merge puede convertirse en una operación que modifica AWS, por lo que cualquier cambio gated debe detenerse antes del merge.

## 11. Vault

Si tienes acceso al vault personal, está en:

`Desktop/herrerogusano's vault/AI Developer Portfolio/AWS Exercises/`

Crea/usa para este ejercicio:

`Exercise 5 - AWS Remote MCP/`

Guarda ahí decisiones y progreso útiles, nunca secretos o identificadores sensibles.

## 12. First response

Antes de modificar archivos, dame solo un resumen corto confirmando:

- dónde encontraste el ZIP;
- dónde crearás el repo;
- que el contenido del ZIP irá en la raíz;
- que encontraste los planes y gates;
- si encontraste `aws-resource-mcp`;
- primera fase pendiente;
- disponibilidad de Git/GitHub;
- cualquier bloqueo inmediato.

Si no hay bloqueos ni gates, después de ese resumen empieza automáticamente. No esperes otra confirmación.


## Mandatory DEV/PROD model

This exercise MUST use two environments.

Git/environment mapping is:

```text
develop → DEV
main    → PROD
```

After the initial bootstrap commit on `main`, create `develop`.

All normal phase branches should be created from `develop`.

Do not treat DEV/PROD as optional even if an older planning paragraph says “evaluate”; the updated `PLAN.md`, `AGENTS.md`, `GATES.md`, and Phase 11/12 rules take precedence.

## Mandatory exercise EXTRA

The final system MUST implement both:

1. structured CloudWatch trace/audit logging for every MCP tool invocation;
2. basic API rate limiting/throttling, initially through API Gateway unless a better reviewed approach is required.

These are completion requirements, not optional enhancements.
