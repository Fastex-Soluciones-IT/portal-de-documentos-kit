---
name: plantilla-desde-word
description: Use when the user wants to turn a Word document (.docx) into a Portal de Documentos (DocAI) template with its fields, datasets, calculations and AI prompts; phrases like "adapta este Word", "genera la plantilla", "crear plantilla desde Word".
license: LicenseRef-Fastex (see LICENSE at https://github.com/Fastex-Soluciones-IT/portal-de-documentos-kit)
---

# Plantilla de Portal de Documentos desde un Word

Esta skill es solo la puerta de entrada: el trabajo lo hace la CLI `docai-kit` del repositorio
`portal-de-documentos-kit`, y el procedimiento completo está en su `AGENTS.md`.

Necesita `git` y [`uv`](https://docs.astral.sh/uv/). Si falta alguno, dilo al usuario y para.

## Pasos

1. Localiza el kit. Si la carpeta actual tiene un `pyproject.toml` con `name = "docai-kit"`, es esa.
   Si no, usa `~/portal-de-documentos-kit` y clónalo si no existe:

   ```bash
   git clone https://github.com/Fastex-Soluciones-IT/portal-de-documentos-kit.git ~/portal-de-documentos-kit
   ```

2. Dentro del kit: `uv sync`.
3. **Lee entero el `AGENTS.md` del kit y síguelo.** Todas las rutas que menciona (`plantillas/`,
   `componentes/`, `docs/`, `schemas/`) son relativas al kit, y los comandos se ejecutan desde él.
4. Copia el Word del usuario como indica `AGENTS.md`. Usa rutas absolutas para el fichero original:
   suele estar fuera del kit.
5. Al terminar, di al usuario la ruta completa de `componentes/<slug>/`.

## Límites

- No importes nada a la plataforma sin confirmación del usuario: entrega el `import` en dry-run.
- Credenciales solo por `DOCAI_HOST`, `DOCAI_USER` y `DOCAI_PASS`, nunca en ficheros.
- El Word y lo generado pueden contener datos de clientes y quedan dentro de un clon de un repositorio
  público: no hagas commit ni push de `plantillas/` ni de `componentes/`.
