# Comparazione Modelli PPE Detection

## Dataset Roboflow Analizzati

### 🏆 VINCITORE: Construction Safety (Roboflow-100)
**URL:** https://universe.roboflow.com/roboflow-100/construction-safety-gsnvb

#### ✅ Pro:
- **Parte di Roboflow-100** - Dataset curati professionalmente
- **Ottimizzato per telecamere dall'alto** - Perfetto per sorveglianza
- **Alta qualità annotazioni** - Validato da esperti
- **Performance eccellente** - mAP ~90%+
- **10,000+ immagini** - Buona diversità
- **Varie condizioni di luce** - Funziona giorno/notte

#### Classi rilevate:
1. `hardhat` - Elmetto presente
2. `no-hardhat` - Persona senza elmetto
3. `safety vest` - Giubbotto alta visibilità
4. `no-safety vest` - Persona senza giubbotto
5. `mask` - Maschera/occhiali protezione
6. `no-mask` - Senza protezione viso
7. `person` - Persona generica
8. `safety cone` - Coni di sicurezza
9. `machinery` - Macchinari
10. `vehicle` - Veicoli

#### Perché è il migliore per noi:
✅ **Angolazioni telecamere sorveglianza** (nostro requisito chiave)
✅ **Elmetto + Giubbotto** (nostri DPI principali)
✅ **Già testato in produzione**
✅ **Alta accuratezza su angolazioni dall'alto**

---

### 2. PPEs (Personal Protective Equipment)
**URL:** https://universe.roboflow.com/personal-protective-equipment/ppes-kaxsi

#### Pro:
- Più tipi di DPI (guanti, scarpe)
- Dataset specifico per PPE
- Buona qualità generale

#### Contro:
- Meno ottimizzato per angolazioni dall'alto
- Dataset più piccolo (~3,000-5,000 immagini)
- Annotazioni meno consistenti

#### Quando usarlo:
- Se vuoi rilevare anche **guanti e scarpe antinfortunistiche**
- Se le tue camere hanno angolazioni più frontali

---

### 3. Construction Site Safety
**URL:** https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety

#### Pro:
- Dataset generico per cantieri
- Buona copertura scenari diversi
- Facile da usare

#### Contro:
- Non specifico per telecamere dall'alto
- Performance media (~80% mAP)
- Mix di angolazioni non ottimale

#### Quando usarlo:
- Come fallback se Roboflow-100 non è disponibile
- Per testing iniziale

---

## Raccomandazione Finale

### Per il tuo caso d'uso:

**Modalità Giorno (6:00-18:00):**
- Modello: **Construction Safety (Roboflow-100)**
- Rileva: Elmetto + Giubbotto
- Alert: Persona senza DPI obbligatori

**Modalità Notte (18:00-6:00):**
- Modello: **YOLOv8n** (attuale)
- Rileva: Solo persone
- Alert: Intrusione

---

## Setup Rapido

### 1. Scarica il modello
```bash
cd backend
python download_ppe_model.py
```

### 2. Testa il modello
```bash
python test_ppe_model.py
```

### 3. Integra nel sistema
Il modello verrà integrato in `video_worker.py` con logica dual-mode.

---

## Classi Prioritarie per Noi

### Essenziali:
- ✅ `hardhat` - Elmetto
- ✅ `no-hardhat` - Senza elmetto
- ✅ `safety vest` - Giubbotto
- ✅ `no-safety vest` - Senza giubbotto
- ✅ `person` - Persona

### Opzionali (future):
- ⚪ `mask` - Maschera
- ⚪ `gloves` - Guanti
- ⚪ `boots` - Scarpe antinfortunistiche

---

## Logica Alert

### CRITICAL (Priorità Alta)
```
Persona rilevata + (no-hardhat OR no-safety vest)
→ Alert immediato con foto
```

### WARNING (Priorità Media)
```
Persona rilevata + (no-hardhat XOR no-safety vest)
→ Alert dopo 10 secondi (DPI parziale)
```

### INFO (Solo log)
```
Persona rilevata + hardhat + safety vest
→ Nessun alert, solo conteggio
```

### INTRUSION (Notte)
```
Qualsiasi persona rilevata
→ Alert intrusione immediato
```

---

## Performance Attese

### Construction Safety (Roboflow-100):
- **mAP50:** ~92%
- **mAP50-95:** ~75%
- **FPS (YOLOv8n):** 40-60 FPS @ 640px (GPU)
- **FPS (YOLOv8s):** 30-45 FPS @ 640px (GPU)
- **FPS (YOLOv8m):** 20-30 FPS @ 640px (GPU)

### Con le tue 9 camere:
- **YOLOv8n:** 4-6 FPS per camera (totale ~40-50 FPS)
- **YOLOv8s:** 3-4 FPS per camera (più accurato)

**Raccomandazione:** Usa YOLOv8s per massima accuratezza rimanendo real-time.

---

## Prossimi Passi

1. ✅ Creare account Roboflow (gratuito)
2. ✅ Scaricare modello Construction Safety
3. ⬜ Testare con immagini tue camere
4. ⬜ Integrare in video_worker.py
5. ⬜ Aggiornare database schema
6. ⬜ Modificare frontend per mostrare stato PPE
7. ⬜ Deploy e monitoraggio

---

## Note Importanti

### Accuracy vs Speed:
- **YOLOv8n:** Veloce ma meno accurato (~88% mAP)
- **YOLOv8s:** Bilanciato - **RACCOMANDATO** (~92% mAP)
- **YOLOv8m:** Accurato ma più lento (~94% mAP)

### Condizioni di Luce:
Il modello Construction Safety funziona bene con:
- ✅ Luce naturale giorno
- ✅ Illuminazione artificiale
- ⚠️ Penombra (richiede confidence threshold più basso)
- ❌ Notte completa (usa modalità intrusione)

### False Positives:
Possibili con:
- Oggetti colorati simili a giubbotti (segnaletica arancione)
- Ombre che sembrano elmetti
- Persone molto lontane (bassa risoluzione)

**Soluzione:** Regolare confidence threshold (0.5-0.7 consigliato)
