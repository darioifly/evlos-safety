# EVLOS Integration - Quick Start

## 1. Abilitazione (30 secondi)

### Opzione A: Via File `.env`

Crea o modifica il file `.env` nella directory principale:

```bash
EVLOS_ENABLED=true
EVLOS_API_URL=http://192.168.1.50:8000/api/v1/alerts/upload
```

### Opzione B: Via `config.py`

Modifica direttamente `backend/config.py`:

```python
EVLOS_ENABLED: bool = True
EVLOS_API_URL: str = "http://192.168.1.50:8000/api/v1/alerts/upload"
```

## 2. Test Configurazione

```bash
cd backend
python test_evlos.py
```

Output atteso:
```
✓ EVLOS is ENABLED
✓ Connection test successful
```

## 3. Test con Alert Reale

1. Avvia backend:
   ```bash
   python main.py
   ```

2. Triggera rilevamento (mostra persona alla camera)

3. Verifica log:
   ```bash
   tail -f logs/detection_*.log | grep EVLOS
   ```

   Dovresti vedere:
   ```
   [INFO] EVLOS alert queued for camera123
   [INFO] EVLOS alert sent successfully: intrusion from camera123 (alert_id=xyz)
   ```

## 4. API Endpoints

### Test Connessione
```bash
curl -X POST http://localhost:7002/evlos/test
```

### Stato Configurazione
```bash
curl http://localhost:7002/evlos/config
```

### Alert Falliti
```bash
curl http://localhost:7002/evlos/failed-alerts
```

## 5. Troubleshooting

### EVLOS non riceve alert

1. **Verifica abilitazione**:
   ```bash
   curl http://localhost:7002/evlos/config
   # Deve mostrare: "enabled": true
   ```

2. **Testa connessione**:
   ```bash
   curl -X POST http://localhost:7002/evlos/test
   ```

3. **Verifica rete**:
   ```bash
   ping 192.168.1.50
   telnet 192.168.1.50 8000
   ```

### Alert falliscono

Controlla directory fallback:
```bash
ls -la data/evlos_failed_alerts/
```

Ogni alert fallito viene salvato come:
- `YYYYMMDD_HHMMSS_intrusion.jpg` (immagine)
- `YYYYMMDD_HHMMSS_intrusion.json` (metadata)

### Camera ID non valida

Se EVLOS risponde con "404 Camera not found":

1. Verifica che il camera_id sia un UUID valido
2. Controlla che la camera sia registrata in EVLOS
3. Testa manualmente:
   ```bash
   curl -X POST http://192.168.1.50:8000/api/v1/alerts/upload \
     -F "file=@test.jpg" \
     -F "camera_id=<YOUR_CAMERA_UUID>" \
     -F "alert_type=intrusion" \
     -F "timestamp=2025-11-17T14:30:25" \
     -F "severity=medium"
   ```

## 6. Configurazione Avanzata

Tutte le opzioni in `config.py` o `.env`:

```python
EVLOS_ENABLED=true                           # Abilita/disabilita
EVLOS_API_URL=http://192.168.1.50:8000/...  # Endpoint EVLOS
EVLOS_TIMEOUT=10                             # Timeout HTTP (secondi)
EVLOS_MAX_RETRIES=3                          # Tentativi retry
EVLOS_FAILED_DIR=data/evlos_failed_alerts    # Dir alert falliti
```

## 7. Mappatura Eventi

| Persone Rilevate | Alert Type EVLOS |
|------------------|------------------|
| 1-2 persone      | `intrusion`      |
| 3+ persone       | `crowd`          |

| Severity Interna | Severity EVLOS |
|------------------|----------------|
| low              | low            |
| medium           | medium         |
| high             | high           |
| critical         | critical       |

## Documentazione Completa

Vedi [EVLOS_INTEGRATION.md](EVLOS_INTEGRATION.md) per:
- Architettura dettagliata
- Gestione errori
- Monitoraggio
- Estensioni future
