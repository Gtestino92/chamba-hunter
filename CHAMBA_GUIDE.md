# Chamba Hunter — Guía mínima de uso

## 1. Job Hunter — refrescar búsquedas y regenerar shortlist

```powershell
python -m chamba_hunter.commands.refresh_search --apply
```

Hace, en orden:

- adquisición de ofertas
- sincronización ATS
- canonicalización
- elegibilidad Argentina
- clasificación backend/ocupación
- skills
- seniority
- matching
- prioridad operativa
- export del shortlist

Salida:

```text
output\chamba-shortlist.xlsx
```

Sin `--apply`, sólo muestra el plan:

```powershell
python -m chamba_hunter.commands.refresh_search
```

---

## 2. Company Hunter — refrescar outreach completo

```powershell
python -m chamba_hunter.commands.refresh_outreach --apply
```

Hace:

- adquisición de empresas
- descubrimiento de empresas Argentina
- descubrimiento de contactos públicos
- limpieza de contactos
- contact intelligence
- priorización de outreach
- export del Excel

Salida:

```text
output\chamba-outreach.xlsx
```

Sin `--apply`, sólo muestra el plan:

```powershell
python -m chamba_hunter.commands.refresh_outreach
```

---

## 3. Sólo regenerar los Excel

### Job shortlist

```powershell
python -m chamba_hunter.commands.export_shortlist `
  --output output\chamba-shortlist.xlsx
```

### Outreach shortlist

```powershell
python -m chamba_hunter.commands.export_outreach_shortlist `
  --profile BACKEND_SOFTWARE_V1 `
  --min-score 45 `
  --min-explore-score 35 `
  --output output\chamba-outreach.xlsx
```

Usar esto después de marcar `APPLY` si sólo querés actualizar la vista sin volver a adquirir datos.

---

## 4. Ver próximos outreach sin regenerar nada

```powershell
python -m chamba_hunter.commands.preview_outreach_decisions `
  --top 20 `
  --min-score 35
```

Muestra los próximos candidatos elegibles y todavía no contactados.

---

## Flujo normal

```text
Cada algunos días:
refresh_search --apply
refresh_outreach --apply

Uso diario:
abrir XLS
→ aplicar / enviar
→ marcar APPLY
→ regenerar XLS
```

La base SQLite es la fuente de verdad. Los Excel son vistas operativas filtradas.
