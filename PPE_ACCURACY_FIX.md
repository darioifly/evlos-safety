# Fix precisione rilevamento PPE (vest/helmet) — 06/07/2026

## Problema

Il sistema generava centinaia di falsi allarmi al giorno (575 solo il 06/07) e
al tempo stesso sopprimeva violazioni reali:

1. **`novest` su sfondo**: un box `NO-Safety Vest` faceva scattare l'alert anche
   senza nessuna persona sotto (macchinari, oggetti scuri → "novest 0.75").
2. **Override colore permissivo**: bastava il 4–8% di pixel "hi-vis" in una ROI
   allargata del 30% (con range HSV larghissimi: rosso H0–25, verde fino a H95)
   per riclassificare un `novest` VERO in `vest` → violazioni reali nascoste.
   In un cantiere pieno di reti arancioni scattava di continuo.
3. **Pre-resize distruttivo**: ogni frame veniva schiacciato a 640×480 (aspect
   ratio distorto) prima dell'inferenza → operai distanti irriconoscibili.
4. **Nessuna coerenza temporale**: alert su singolo frame + cooldown 4s → lo
   sfarfallio del modello diventava un'inondazione di alert (1 ogni 5–15s).
5. **Persone troppo lontane giudicate comunque**: a 40px di altezza il gilet
   non è fisicamente risolvibile, ma il modello emetteva verdetti casuali.
6. **Crash-loop CUDA**: in caso di errore CUDA il worker riconnetteva ogni
   secondo all'infinito (log di giugno: 8+ MB/giorno di soli errori).
7. Config morta: `ppeRules`, `detectionMode: dual` e `schedule` in config.json
   erano ignorati dal codice; `ppe_confidence` del preset mai usato.

## Soluzione

### Nuovo modulo `backend/services/ppe_logic.py` (logica pura, unit-testata)
- **Gating persona**: un box violazione (`novest`/`nohat`) conta SOLO se
  associato a una persona rilevata (centro-nel-box espanso verso l'alto del
  15% per gli elmetti, oppure IoU > 0.25). I box su sfondo vengono ignorati.
  Le persone "possono possedere" item già da conf 0.35 (persone
  troncate/occluse), ma contano come presenza solo da 0.50.
- **Vest-veto**: se sulla stessa persona coesistono `vest` e `novest`
  (NMS è per-classe, capita spesso), vince la compliance — niente alert.
- **Eligibilità dimensionale**: persone alte meno di `minPersonHeightRatio`
  (default 6% dell'altezza frame) NON vengono giudicate per i DPI.
- **Soglie per classe** (`classConfidence`): violazioni ≥ 0.80,
  compliance (vest/hat) ≥ 0.45, person ≥ 0.50. Il `ppe_confidence` del preset
  per-camera può solo ALZARE le soglie violazione.
- **Voto temporale N-di-M con scadenza** (`TemporalViolationFilter`): una
  violazione deve comparire in ≥3 degli ultimi 5 frame analizzati E i voti
  devono essere recenti (`temporalMaxAgeSeconds`, default 90s) — i voti
  stantii di ieri sera non si combinano col rumore di stamattina.
- Fallback per modelli senza classi "no" esplicite conservato (per-persona,
  solo su persone a piena confidenza). Modelli SENZA classe person
  (workspace_safety.pt) giudicati direttamente sui box espliciti (come il
  comportamento legacy, ma con soglia 0.80 + voto temporale).

### `backend/services/video_worker_manager.py`
- `_process_frame`: **niente più resize 640×480**; inferenza a risoluzione
  nativa con `imgsz` configurabile (`inferenceSize`, default 1280).
  Modalità **dual** ora reale: camere in `ppe` passano a intrusion di notte
  secondo `schedule` (il modello PPE su frame notturni IR produce solo rumore).
- `_has_hivis_color` **rigoroso**: nessuna espansione ROI, soglia default 20%,
  solo range fluorescenti stretti (orange/yellow/green; red opzionale),
  niente modalità "distant" rilassata, ROI < 400px → non giudicabile.
- `_process_ppe_mode` riscritto sopra `ppe_logic.evaluate_ppe` + voto
  temporale + **pacing realert** (`alertRealertSeconds`, default 120s: una
  violazione persistente ricorda ogni 2 minuti invece di inondare).
- **Frame di evidenza**: se la conferma temporale arriva su un frame "pulito",
  l'alert usa l'ultimo frame che mostrava davvero la violazione.
- Reset del voto temporale al cambio giorno/notte (dual mode).
- **Ladder anti-OOM**: CUDA out-of-memory a imgsz 1280 → degrada a 960 → 640
  con log chiaro, invece di andare in crash-loop mascherato da "Stream error".
- Backoff esponenziale (5s→300s) quando lo stream/inferenza muore subito
  dopo la connessione (anti crash-loop CUDA).
- Cast protetti su tutti i valori config hot-reloadabili (un refuso in
  config.json non manda più il worker in crash-loop).
- Immagini alert limitate a 1920px di larghezza (i frame ora sono a
  risoluzione nativa; 3 JPEG per alert).
- Crop e payload NX Witness calcolati sui box processati (non sull'output
  grezzo a bassa confidenza).
- Confidenza intrusion: vince il preset per-camera se ≥ 0.4, altrimenti
  fallback sul globale (i preset stantii non aprono le cateratte).

### `backend/config.json` — nuove chiavi
```json
"classConfidence": {"person":0.5, "vest":0.45, "hat":0.45, "novest":0.8, "nohat":0.7},
"inferenceSize": 1280,
"minPersonHeightRatio": 0.06,
"temporalWindow": 5,
"temporalMinHits": 3,
"temporalMaxAgeSeconds": 90,
"alertRealertSeconds": 120,
"vestColorOverride": {"enabled":true, "threshold":0.2, "colors":["orange","yellow","green"]}
```

## Backtest sui 1.746 alert storici + giudizio visivo cieco (07/07/2026)

Replay dell'intero archivio alert (15/05–11/06 = vecchio codice, 06–07/07 =
nuovo codice) con la nuova pipeline (`backtest.py`), più 73 campioni
stratificati giudicati alla cieca da 2 agenti indipendenti (accordo 95%).
Trovato e corretto con i DATI:

1. **Override colore → DISABILITATO di default**: 8/8 soppressioni da
   override erano violazioni VERE (magliette arancioni/hi-vis di terzi
   dentro il box novest ingannano qualunque statistica di colore).
2. **Vest-veto → regola stesso-torso** (IoU ≥ 0.45 tra box novest e box
   vest): il veto a livello di "proprietario" uccideva 4/4 violazioni vere
   nelle scene di gruppo (il gilet del collega associava anche al violatore).
3. **novest 0.80 → 0.75**: la banda 0.75–0.80 era all'~92% violazioni vere;
   il flicker resta filtrato dal voto 3-di-5.

Risultato finale sul corpus storico (solo frame diurni, vecchio codice):
- ritenzione **per episodio** (cluster ≤10 min): **75%** (177/236); persi 9
  episodi multi-frame + 50 blip da singolo frame (che il filtro temporale
  sopprimerebbe comunque).
- precisione degli alert mantenuti (campione giudicato): **~92%**.
- 17% dei vecchi alert era notturno → ora gestito come intrusion (corretto:
  i campioni notturni mostrano pattuglie/persone in cantiere di notte).
- Gli alert del NUOVO codice live (06–07/07) giudicati: **11/12 violazioni
  vere.**

**Nota operativa**: il grosso del "flood" storico erano violazioni REALI
ricorrenti nelle zone uffici/ingresso (Sessa 2, Dragoni), ri-allertate ogni
4 s dal vecchio codice. Ora il pacing è 1 alert/120 s per violazione
persistente. Se quelle zone non richiedono DPI, la soluzione è una maschera
di zona per-camera (feature futura), non alzare le soglie.

## Trade-off dichiarati (review avversariale multi-agente, 16 agenti)
- **Camera larga (Velletri)**: persone < 6% dell'altezza frame NON vengono
  giudicate per i DPI (a quella distanza il verdetto del modello è rumore —
  meglio "non giudicabile" che sbagliato). Il monitoraggio DPI affidabile a
  quella distanza richiede una camera più vicina/zoomata o un modello
  fine-tunato sul sito.
- **Banda 0.55–0.79**: un `novest` sotto 0.80 non allerta mai (precision
  first). Se sul campo mancano violazioni vere, abbassare
  `classConfidence.novest` gradualmente (0.75 → 0.70) osservando i falsi.
- **Soglie asimmetriche**: `nohat` a 0.70 (sui filmati reali le violazioni
  casco VERE uscivano a 0.77–0.81 e i falsi nohat non erano un problema),
  `novest` a 0.80 (era la fonte dei falsi allarmi).
- **Test suite**: 57 test su `ppe_logic` + 34 preesistenti = 91.

## Validazione E2E su frame di alert reali (modello vero, `validate_fix.py`)
| Frame | Vecchio verdetto | Nuovo verdetto (single-frame) |
|---|---|---|
| Velletri novest 0.81 su persona | ALERT | vest_missing (+ richiede 3/5 frame) |
| Velletri novest 0.83 distante | ALERT | vest_missing (+ richiede 3/5 frame) |
| Velletri novest 0.78 borderline | ALERT | nessuna violazione |
| Pontinia nohat 0.80 (vera, con gilet ok) | ALERT | helmet_missing ✓ |
| Pontinia nohat 0.79 (vera) | ALERT | helmet_missing ✓ |

Nota: sul venv del .21 CUDA dà "no kernel image is available for execution
on the device" → il torch installato non supporta la GPU di quella macchina
(probabile causa del crash-loop CUDA nei log di giugno). La validazione è
stata eseguita su CPU. Se si ridistribuisce lì, reinstallare torch con la
build CUDA corretta per la GPU.

## Tuning sul campo
- GPU debole / OOM → abbassare `inferenceSize` a 960 o 640.
- Troppi falsi `novest` residui → alzare `classConfidence.novest` a 0.85–0.90.
- Violazioni vere mancate su camere vicine → abbassare `minPersonHeightRatio`.
- Gilet sbiaditi/grigi non riconosciuti dall'override → abbassare
  `vestColorOverride.threshold` a 0.15 (mai sotto 0.12).

## Test
- `backend/tests/test_ppe_logic.py`: 45 test sulla logica pura.
- Suite completa: `venv\Scripts\python.exe -m pytest tests -q` dal dir backend.

## Deploy
⚠️ L'istanza LIVE gira su **192.168.1.28:7002** (venv, utente iflys) e il suo
codice è PIÙ RECENTE di questa copia (ha `face_blur_enabled` nei preset):
NON sovrascrivere alla cieca `video_worker_manager.py` sul .28 — portare le
modifiche sul file reale (il diff è in `changes.diff`). `ppe_logic.py` e
`test_ppe_logic.py` sono file nuovi e si copiano così come sono.

Mitigazioni già applicate al volo sul .28 via API il 06/07/2026 (~16:20):
- preset 7 "Biormedano": `cooldown_seconds` 4 → 60
- `vestColorOverride`: threshold 0.08 → 0.20, tolto "red"
- aggiunte le nuove chiavi in config.json (inerti finché non si deploya il codice)
- backup config originale: `live_config_backup_20260706.json`
