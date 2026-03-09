# Integrazione EVLOS

Documentazione per l'integrazione con la piattaforma esterna EVLOS per l'invio di alert.

## Panoramica

Quando il sistema rileva un'anomalia (persona rilevata), può inviare automaticamente l'immagine e i metadati a EVLOS tramite API HTTP.

**Caratteristiche**:
- Invio asincrono (non blocca il processing video)
- Retry automatico con exponential backoff (3 tentativi: 2s, 4s, 8s)
- Fallback locale per alert falliti
- Completamente configurabile e disabilitabile

## Configurazione

### 1. Variabili di Configurazione

Aggiungi queste variabili in `config.py` (o in `.env`):

```python
# EVLOS Integration
EVLOS_ENABLED=false              # true per abilitare, false per disabilitare
EVLOS_API_URL=http://192.168.1.50:8000/api/v1/alerts/upload
EVLOS_TIMEOUT=10                 # Timeout richiesta HTTP (secondi)
EVLOS_MAX_RETRIES=3              # Numero massimo di tentativi
EVLOS_FAILED_DIR=data/evlos_failed_alerts  # Directory alert falliti
```

### 2. Installazione Dipendenze

```bash
cd backend
pip install -r requirements.txt
```

Le dipendenze necessarie sono:
- `requests` (già presente)
- `Pillow` (aggiunta per test)

### 3. Abilitazione

Per abilitare l'integrazione, imposta:

```python
EVLOS_ENABLED=true
```

O via API runtime (non persistente):

```bash
curl -X POST http://localhost:7002/evlos/enable
```

## Mappatura Eventi

### Tipi di Alert

Il sistema attualmente rileva solo **persone**. La mappatura verso i tipi EVLOS è:

| Tipo Interno | Persone | Tipo EVLOS |
|-------------|---------|------------|
| person_detection | 1-2 | `intrusion` |
| person_detection | 3+ | `crowd` |

### Severity

La severity viene calcolata automaticamente in base a:
- Numero di persone rilevate
- Confidenza AI

| Alert Level | Severity EVLOS |
|-------------|----------------|
| low | low |
| medium | medium |
| high | high |
| critical | critical |

## Flusso di Invio

1. **Rilevamento** → Il sistema rileva persone e triggera un alert
2. **Screenshot** → Viene salvato uno screenshot con bounding box
3. **NxWitness** → Viene inviato event + bookmark a NxWitness
4. **EVLOS (async)** → Se abilitato, viene inviato a EVLOS in background
5. **Retry** → In caso di fallimento, retry automatico (max 3 volte)
6. **Fallback** → Se tutti i retry falliscono, salva localmente

## API Endpoints

### GET /evlos/config

Ottieni configurazione attuale EVLOS.

**Risposta**:
```json
{
  "enabled": false,
  "api_url": "http://192.168.1.50:8000/api/v1/alerts/upload",
  "timeout": 10,
  "max_retries": 3,
  "failed_dir": "data/evlos_failed_alerts"
}
```

### POST /evlos/test

Testa la connessione a EVLOS con un alert dummy.

**Risposta successo**:
```json
{
  "success": true,
  "message": "Connection successful! Alert ID: 123e4567-e89b-12d3-a456-426614174000",
  "alert_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Risposta errore**:
```json
{
  "success": false,
  "message": "Connection failed: HTTP 404: Camera not found",
  "alert_id": null
}
```

### GET /evlos/failed-alerts

Ottieni lista di alert falliti salvati localmente.

**Risposta**:
```json
{
  "count": 2,
  "directory": "data/evlos_failed_alerts",
  "alerts": [
    {
      "camera_id": "550e8400-e29b-41d4-a716-446655440000",
      "alert_type": "intrusion",
      "severity": "medium",
      "confidence": 0.85,
      "timestamp": "2025-11-17T14:30:25",
      "error": "Connection timeout after 3 retries",
      "json_file": "20251117_143025_intrusion.json",
      "image_file": "20251117_143025_intrusion.jpg"
    }
  ]
}
```

### POST /evlos/enable

Abilita EVLOS a runtime (non persistente).

### POST /evlos/disable

Disabilita EVLOS a runtime (non persistente).

## Testing

### Test di Connessione

```bash
# Via API
curl -X POST http://localhost:7002/evlos/test

# Via Python
from integrations.evlos_client import evlos_client
result = evlos_client.test_connection()
print(result)
```

### Test con Alert Reale

1. Abilita EVLOS: `EVLOS_ENABLED=true`
2. Avvia il backend: `python main.py`
3. Triggera un rilevamento (mostra una persona alla camera)
4. Controlla i log per conferma invio:

```
[INFO] EVLOS alert queued for 550e8400-e29b-41d4-a716-446655440000
[INFO] EVLOS alert sent successfully: intrusion from 550e8400-... (alert_id=abc123)
```

### Simulazione Fallimento

Per testare il fallback locale:

1. Imposta URL errato: `EVLOS_API_URL=http://192.168.1.99:9999/fake`
2. Triggera un alert
3. Controlla directory fallback: `data/evlos_failed_alerts/`

Dovresti trovare:
- `YYYYMMDD_HHMMSS_intrusion.jpg` (immagine)
- `YYYYMMDD_HHMMSS_intrusion.json` (metadata)

## Formato Dati Inviati

### Multipart Form Data

```
POST http://192.168.1.50:8000/api/v1/alerts/upload
Content-Type: multipart/form-data

Fields:
- file: [binary JPEG image]
- camera_id: "550e8400-e29b-41d4-a716-446655440000"
- alert_type: "intrusion"
- timestamp: "2025-11-17T14:30:25.123456"
- severity: "medium"
- confidence: "0.85"
```

## Gestione Errori

### Errori HTTP 4xx (Client)

NON viene fatto retry automatico (errore permanente).

Esempi:
- `400` - Parametri invalidi
- `403` - IP non autorizzato
- `404` - Camera non trovata

L'alert viene salvato in `data/evlos_failed_alerts/` per retry manuale.

### Errori HTTP 5xx e Timeout

Viene fatto retry automatico (3 volte con exponential backoff).

Esempi:
- `500` - Errore interno EVLOS
- `503` - Servizio temporaneamente non disponibile
- Timeout connessione
- Errori di rete

Se dopo 3 retry ancora fallisce → salvato localmente.

## Logging

Il sistema logga tutte le operazioni EVLOS:

```
[INFO] EVLOS Client initialized (enabled=true, url=http://192.168.1.50:8000/...)
[DEBUG] EVLOS alert queued for async sending: intrusion from camera123
[INFO] EVLOS alert sent successfully: intrusion from camera123 (alert_id=xyz789)
[WARNING] EVLOS send attempt 1/3 failed: Connection timeout
[INFO] Retrying EVLOS send in 2s...
[ERROR] EVLOS send permanently failed after 3 attempts: Connection timeout
[INFO] Failed alert saved to data/evlos_failed_alerts: 20251117_143025_intrusion
```

## Monitoraggio

### Check Status

```bash
# Configurazione
curl http://localhost:7002/evlos/config

# Alert falliti
curl http://localhost:7002/evlos/failed-alerts
```

### Metriche

Il sistema usa il logging esistente. Per monitorare:

```bash
# In tempo reale
tail -f backend/logs/detection_*.log | grep EVLOS

# Contare alert inviati
grep "EVLOS alert sent successfully" backend/logs/detection_*.log | wc -l

# Contare fallimenti
grep "EVLOS send permanently failed" backend/logs/detection_*.log | wc -l
```

## Troubleshooting

### EVLOS non invia alert

1. Verifica abilitazione: `EVLOS_ENABLED=true`
2. Testa connessione: `curl -X POST http://localhost:7002/evlos/test`
3. Controlla logs: `grep EVLOS backend/logs/detection_*.log`

### Alert falliscono sempre

1. Verifica URL: `EVLOS_API_URL` corretto?
2. Verifica rete: `ping 192.168.1.50`
3. Verifica porta: `telnet 192.168.1.50 8000`
4. Testa manualmente:

```bash
curl -X POST http://192.168.1.50:8000/api/v1/alerts/upload \
  -F "file=@test.jpg" \
  -F "camera_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "alert_type=intrusion" \
  -F "timestamp=2025-11-17T14:30:25" \
  -F "severity=medium" \
  -F "confidence=0.85"
```

### Camera ID non valido

EVLOS richiede UUID. Se le nostre camera hanno ID non-UUID, crea mappatura in `config.py`:

```python
CAMERA_ID_TO_UUID = {
    "camera_1": "550e8400-e29b-41d4-a716-446655440000",
    "camera_zona_nord": "660f9511-f39c-52e5-b827-557766551111",
}
```

Poi modifica `evlos_client.py` per usare la mappatura.

### Performance

L'invio EVLOS è **completamente asincrono** e non blocca il video processing:
- Usa ThreadPoolExecutor con 4 worker
- Timeout di 10 secondi per richiesta
- Non influenza FPS o latenza detection

Se noti problemi di performance:
1. Disabilita temporaneamente: `EVLOS_ENABLED=false`
2. Aumenta timeout: `EVLOS_TIMEOUT=20`
3. Riduci retry: `EVLOS_MAX_RETRIES=1`

## Sicurezza

- EVLOS usa IP whitelist (siamo già autorizzati)
- Nessun header di autenticazione richiesto
- Le immagini contengono dati sensibili → assicurati che EVLOS sia in rete privata
- Non esporre pubblicamente l'endpoint `/evlos/test`

## Estensioni Future

Quando implementerai nuovi tipi di rilevamento (DPI, cadute, etc.), aggiorna la mappatura in `evlos_client.py`:

```python
self.alert_type_mapping = {
    'person_detection': 'intrusion',
    'helmet_missing': 'no_ppe',      # NUOVO
    'vest_missing': 'no_ppe',        # NUOVO
    'person_fall': 'fall_detection', # NUOVO
    # ... altri
}
```

Il resto funzionerà automaticamente.

## Supporto

Per problemi o domande:
1. Controlla i log: `backend/logs/detection_*.log`
2. Controlla alert falliti: `data/evlos_failed_alerts/`
3. Testa connessione: `POST /evlos/test`
