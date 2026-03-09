# EVLOS Integration - Frontend Guide

## Interfaccia Utente EVLOS nel Frontend

È stata aggiunta una nuova sezione nella pagina di **Configurazione** per gestire l'integrazione EVLOS direttamente dal frontend.

---

## Dove Trovarla

1. Avvia il frontend
2. Vai alla pagina **Configuration** (icona ⚙️ Settings)
3. Scorri fino alla sezione **"EVLOS External Platform Integration"** (box arancione/amber)
   - Si trova dopo "NxWitness Alert Integration"
   - Prima di "Confidence Threshold"

---

## Funzionalità Disponibili

### 1. Toggle Enable/Disable

**Switch On/Off** in alto a destra nella sezione EVLOS.

- **ON (verde)**: EVLOS abilitato, invierà alert alla piattaforma esterna
- **OFF (grigio)**: EVLOS disabilitato, nessun invio

**Come funziona**:
- Click sul toggle → abilita/disabilita EVLOS a runtime
- Mostra messaggio di conferma: "EVLOS enabled/disabled successfully"
- Lo stato si aggiorna automaticamente ogni 5 secondi

**⚠️ Importante**:
- Il toggle modifica solo lo stato **runtime** (non persistente)
- Al restart del backend, torna al valore in `config.py`
- Per rendere permanente: modifica `EVLOS_ENABLED=true` in backend config

---

### 2. Visualizzazione Configurazione

Box bianco che mostra:
- **Status**: ✓ Enabled / ○ Disabled
- **Timeout**: Secondi timeout richiesta HTTP (es: 10s)
- **API URL**: Endpoint EVLOS completo
- **Max Retries**: Numero tentativi retry (es: 3)
- **Backoff**: Tempi tra retry (2s, 4s, 8s)

---

### 3. Test Connessione

**Pulsante "Test EVLOS Connection"**

Click → Invia un alert di test a EVLOS con:
- Immagine dummy (1x1 pixel rosso)
- Camera ID test: `00000000-0000-0000-0000-000000000000`
- Alert type: `intrusion`
- Severity: `low`

**Risultati**:
- ✅ **Success**: "EVLOS connection successful!" (verde)
- ❌ **Error**: "Connection failed. Check EVLOS API endpoint." (rosso)

**Note**:
- Pulsante disabilitato se EVLOS è OFF
- Animazione "pulse" durante test
- Messaggio scompare dopo 5 secondi

---

### 4. Informazioni Mappatura Alert

Box che mostra come gli eventi interni vengono mappati a EVLOS:

| Evento Rilevato | Alert Type EVLOS |
|----------------|------------------|
| 1-2 persone | `intrusion` |
| 3+ persone | `crowd` |
| Violazione PPE (futuro) | `no_ppe` |

---

### 5. Avvisi e Note

#### Quando EVLOS è Disabilitato

Box arancione di warning:
```
⚠️ EVLOS is currently disabled

Enable the toggle above to start sending alerts to the external platform.
Make sure the EVLOS API is reachable before enabling.
```

#### Nota su Runtime vs Config

Box grigio informativo:
```
Note: Toggle changes are runtime-only.
To persist, set EVLOS_ENABLED=true in backend config and restart.
```

---

## Come Usare (Workflow Tipico)

### Scenario 1: Abilitare EVLOS per la Prima Volta

1. **Apri Configuration** nel frontend
2. **Scorri a EVLOS section** (box arancione)
3. **Verifica API URL** nel box bianco (es: `http://192.168.1.50:8000/...`)
4. **Click sul Toggle** (da OFF → ON)
5. **Attendi conferma** "EVLOS enabled successfully!" (verde)
6. **Click "Test EVLOS Connection"**
7. **Verifica risultato**:
   - ✅ Success → EVLOS funziona, pronto all'uso
   - ❌ Error → Controlla rete/endpoint EVLOS

### Scenario 2: Disabilitare Temporaneamente

1. **Click sul Toggle** (da ON → OFF)
2. **Conferma** "EVLOS disabled successfully!"
3. Gli alert NxWitness continuano a funzionare normalmente
4. EVLOS non riceverà più alert fino a ri-abilitazione

### Scenario 3: Testare Connessione

1. **Con EVLOS già abilitato** (toggle ON)
2. **Click "Test EVLOS Connection"**
3. **Osserva log backend** (opzionale):
   ```bash
   tail -f backend/logs/detection_*.log | grep EVLOS
   ```
4. **Risultato immediato** nel frontend

---

## Screenshot UI (Descrizione)

### Sezione EVLOS - Vista Completa

```
┌─────────────────────────────────────────────────────┐
│ EVLOS External Platform Integration          [ON/OFF│
│ Send alert images and metadata to external EVLOS    │
├─────────────────────────────────────────────────────┤
│ ┌─── Configuration ───────────────────────────────┐ │
│ │ Status: ✓ Enabled      Timeout: 10s            │ │
│ │ API URL: http://192.168.1.50:8000/api/v1/...   │ │
│ │ Max Retries: 3         Backoff: 2s, 4s, 8s     │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ ┌─────────────────────────────────────────────────┐ │
│ │       📤 Test EVLOS Connection                  │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ ✅ EVLOS connection successful!                     │
│                                                     │
│ ℹ️ How EVLOS works:                                 │
│ • Sends alert images + metadata                    │
│ • Auto-retry with exponential backoff              │
│ • Failed alerts saved locally                      │
│ • Fully asynchronous - doesn't block processing    │
│                                                     │
│ Alert Type Mapping:                                │
│ 1-2 persons → intrusion                            │
│ 3+ persons → crowd                                 │
│ PPE violation → no_ppe                             │
└─────────────────────────────────────────────────────┘
```

---

## Aggiornamento Automatico

La configurazione EVLOS si **ricarica automaticamente ogni 5 secondi** dal backend.

Questo significa:
- Se abiliti EVLOS dal backend (API o config), il frontend lo mostra subito
- Se disabiliti dal backend, il toggle si aggiorna automaticamente
- Non serve refresh manuale della pagina

---

## Troubleshooting Frontend

### Toggle non risponde

1. Controlla console browser (F12) per errori JavaScript
2. Verifica che backend sia in esecuzione: `http://localhost:7002/health`
3. Testa endpoint EVLOS manualmente:
   ```bash
   curl http://localhost:7002/evlos/config
   ```

### Test Connection fallisce sempre

1. **Verifica toggle ON**: Il test funziona solo se EVLOS abilitato
2. **Controlla backend logs**:
   ```bash
   grep EVLOS backend/logs/detection_*.log
   ```
3. **Testa connessione EVLOS** dalla rete:
   ```bash
   ping 192.168.1.50
   telnet 192.168.1.50 8000
   ```

### Status non si aggiorna

1. **Attendi 5 secondi**: Auto-refresh ogni 5s
2. **Refresh manuale pagina**: F5
3. **Controlla backend**: Endpoint `/evlos/config` risponde?
   ```bash
   curl http://localhost:7002/evlos/config
   ```

---

## File Modificati per Frontend

1. **[frontend/src/lib/api.js](frontend/src/lib/api.js)**
   - Aggiunte funzioni API EVLOS:
     - `evlosAPI.getConfig()`
     - `evlosAPI.testConnection()`
     - `evlosAPI.getFailedAlerts()`
     - `evlosAPI.enable()`
     - `evlosAPI.disable()`

2. **[frontend/src/components/ConfigPanel.jsx](frontend/src/components/ConfigPanel.jsx)**
   - Nuova sezione UI EVLOS (righe 520-667)
   - State management: `evlosTestStatus`, `evlosToggleStatus`
   - Query: `evlosConfig` con refetch ogni 5s
   - Handlers: `handleEvlosTest()`, `handleEvlosToggle()`

---

## Funzionalità Avanzate (Future)

Possibili estensioni (non ancora implementate):

- [ ] **Visualizzazione Alert Falliti**: Mostra lista alert salvati localmente
- [ ] **Retry Manuale**: Pulsante per reinviare alert falliti
- [ ] **Statistiche Invio**: Contatore success/failed alerts
- [ ] **Log Live**: Stream log EVLOS in tempo reale
- [ ] **Configurazione URL**: Modifica API URL dal frontend

---

## Compatibilità

- **Browser**: Chrome, Firefox, Edge (moderni)
- **Mobile**: Responsive design, touch-friendly
- **Backend**: Richiede backend con EVLOS integration (v1.0+)

---

## Link Utili

- **Backend EVLOS Guide**: [EVLOS_QUICK_START.md](backend/EVLOS_QUICK_START.md)
- **Technical Docs**: [EVLOS_INTEGRATION.md](backend/EVLOS_INTEGRATION.md)
- **API Reference**: `http://localhost:7002/docs` (FastAPI Swagger)

---

## Domande Frequenti (FAQ)

**Q: Posso abilitare EVLOS senza restart del backend?**
A: Sì! Usa il toggle nel frontend. È runtime-only, ma funziona immediatamente.

**Q: Come rendere l'abilitazione permanente?**
A: Modifica `EVLOS_ENABLED=true` in `backend/config.py` e riavvia backend.

**Q: Il test fallisce ma il toggle è ON**
A: Controlla che l'endpoint EVLOS sia raggiungibile dalla rete del backend. Usa ping/telnet per verificare.

**Q: Gli alert vengono inviati anche se il test fallisce?**
A: Sì, il test è indipendente. Gli alert reali verranno comunque tentati e, se falliscono, salvati localmente.

**Q: Posso vedere gli alert falliti?**
A: Attualmente via API: `curl http://localhost:7002/evlos/failed-alerts`. UI in arrivo.

---

**Frontend EVLOS Integration - Ready to Use! 🚀**
