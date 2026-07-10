# Fine-tune experiment — 10/07/2026 (NON deployato)

Obiettivo: insegnare al modello (wesjos helmet_vest.pt) a riconoscere i gilet
**teal/verde** a livello di modello, invece del cerotto color-override.

## Pipeline (rigorosa, riproducibile)
1. `ensemble_label.py` — auto-labeling di 2108 frame d'archivio con 3 modelli
   PPE (wesjos + construction_safety + workspace_safety), correzione teal, e
   **corroborazione vest** (un gilet vale solo se ≥2 modelli concordano o
   conf≥0.60 — per non insegnare gilet inesistenti → violazioni mancate).
2. `render_labels.py` + audit con giudici vision (Claude): correzione teal
   **29/32 corretta, 0 sbagliata**; etichette novest **98%** corrette; vest
   72% (spurie ridotte dalla corroborazione). 11 frame "bad".
3. `curate_dataset.py` — esclusi 17 frame (11 bad + 6 ad alta ambiguità) →
   **2091 frame**, 90% con etichettatura vest completa. Split per data.
4. `train_ft.py` — fine-tune da helmet_vest.pt, imgsz 960 batch 4 (1280/8
   sforava i 12GB → spill in RAM), 60 epoche, lr auto (AdamW), **hsv_h basso**
   (per non alterare il colore teal). VLM in pausa per liberare la GPU.
5. `ft_accept_gate.py` — GATE su frame reali giudicati.

## Esito: NON supera il confronto pratico → NON deployato
Gate (modello, senza override colore):
- teal riconosciuto: OLD **0/4** → FINE-TUNE **1/4**  (+1, ma debole)
- violazioni vere mantenute: OLD **15/19** → FINE-TUNE **14/19**  (**-1**)
- val per-classe: vest è la classe più debole (mAP50 0.77, P 0.64) vs
  novest 0.90 / person 0.91.

**Perché non basta:** solo 26 esempi teal, di fatto un operaio in una scena
(Sessa 1). Impossibile generalizzare un nuovo COLORE di gilet da così pochi
esempi mono-scena. Il **color-override** (già in produzione) risolve il teal
**4/4** e generalizza meglio perché non dipende dalla scena. Il fine-tune
inoltre **perde 1 violazione vera**: per un sistema di sicurezza è inaccettabile
regredire il recall per un beneficio che l'override già copre.

## Decisione
- Modello live resta **helmet_vest.pt + teal color-override**.
- `best.pt` archiviato: `models/ppe/ft_experiment_20260710_best.pt` (per riferimento).
- Via per un vero fix a livello di modello: raccogliere gilet teal/verdi da
  **più cantieri/operai** (diversità), poi ri-addestrare. Con i dati attuali
  l'override è la soluzione migliore.
