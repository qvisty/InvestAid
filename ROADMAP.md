# InvestAid - Roadmap og kommende funktioner

Disse funktioner er planlagt til fremtidig implementering. De bygges **ikke** nu, men er dokumenteret her til reference.

---

## Kommende opgaver

### 1. E-mail notifikationer
**Formål:** Systemet sender automatisk e-mails, så du kan holde øje uden at overvåge computeren aktivt.

Notifikationer der ønskes:
- **Handel udført** — køb eller salg gennemført (symbol, antal, pris, strategi)
- **Stop-loss aktiveret** — position lukket pga. tab (symbol, tab i kr/%)
- **Take-profit aktiveret** — position lukket med gevinst
- **Daglig status** — samlet porteføljeværdi, dagens P&L, åbne positioner
- **Fejlalarm** — hvis botten crasher eller mister forbindelsen
- **E-mail kill-switch (retur-svar)** — se afsnit 1b nedenfor

Teknologi: `smtplib` (Gmail/Outlook SMTP) eller SendGrid API. Konfigureres med e-mailadresse i `.env`.

---

### 1b. E-mail kill-switch (to-vejs kommunikation)
**Formål:** Hvis du modtager en alarm-e-mail fra systemet og vil stoppe al handel øjeblikkeligt, svarer du blot retur på mailen med et kodeord. Systemet overvåger din indbakke og stopper, hvis det ser svaret.

Sådan skal det fungere:
1. Systemet sender en alarm-e-mail (f.eks. "Stop-loss aktiveret — portefølje faldet 8% i dag")
2. Du ser mailen på din telefon og er bekymret
3. Du svarer retur på mailen med kodeordet `STOP` (eller `STANDS`)
4. Systemet tjekker indbakken løbende (f.eks. hvert minut via IMAP)
5. Når svaret opdages, sættes en global `trading_halted = True` flag
6. Al yderligere handel, ordreafgivelse og strategi-kørsel stoppes øjeblikkeligt
7. Systemet sender en bekræftelses-e-mail: "Handel stoppet. Systemet kører stadig men handler ikke."
8. Genoptagelse kræver manuel genstart af botten (bevidst — for at tvinge dig til at tage stilling)

Teknisk implementering:
- IMAP-polling af din e-mailindbakke (imaplib, standard Python-bibliotek)
- Tjekker kun svar-tråde til mails sendt af InvestAid (via Message-ID header)
- Kodeordet konfigureres i `.env` (ikke hardkodet)
- Kill-switch-tilstanden gemmes i databasen og overlever et program-crash/genstart
- Systemet logger tydeligt hvornår kill-switchen blev aktiveret og af hvilken e-mail

---

### 2. 5-års simulering (Monte Carlo / historisk replay)
**Formål:** Kør hele programmets kode igennem med historiske data for at se, hvad der ville være sket — inden rigtige penge investeres.

Ønskede funktioner:
- Kør alle tre strategier (EMA, RSI, HRP) på 5 års historiske data
- Vis graf: porteføljeværdi over tid, drawdown, månedlig P&L
- Sammenlign mod simpel buy-and-hold (S&P 500)
- Monte Carlo-variation: simulér 1.000 mulige fremtidsscenarier baseret på historisk volatilitet
- Vis worst-case, median og best-case udfald
- Identificér automatisk perioder der ville have crashet systemet

Teknologi: VectorBT (allerede i projektet), yfinance historik, NumPy Monte Carlo.

---

### 3. Markedssimulering og stress-test
**Formål:** Afspil kendte markedskriser for at se, om systemet overlever — og om stop-loss fungerer som forventet.

Scenarier der bør testes:
- COVID-krakket (feb–mar 2020, -34% på 33 dage)
- Finanskrisen 2008 (–57% over 17 måneder)
- Dot-com krisen 2000–2002
- Flash Crash 2010 (–9% på én dag)

Funktioner:
- Kør bot-logikken "hurtigt" mod historiske data (1 dag = 1 sekund)
- Vis præcis hvilke beslutninger botten tog i krisen
- Tjek om stop-loss og daglig tabsgrænse virkede som forventet
- Output: rapport med "hvad ville der være sket"

---

### 4. Intelligent positionsstørrelse (fee-bevidsthed)
**Formål:** Sikre at handelsgebyrer ikke æder afkastet — særligt vigtigt for små porteføljer.

Regler der skal implementeres:
- **Minimum ordrestørrelse**: Aldrig køb for under ~$50 (gebyr-til-handels-ratio under 1%)
- **Alpaca har 0% kurtage på aktier/ETF'er**, men krypto har ~0.15–0.25% — tages med i beregning
- Advar brugeren hvis den konfigurerede max_position_pct giver ordrer der er for små til at give mening
- Dynamisk tilpasning: jo mindre portefølje, jo færre og større positioner

---

### 5. Automatisk risikospredning ved vækst
**Formål:** Når porteføljen vokser, spredt risikoen automatisk på flere aktiver og aktivklasser.

Foreslåede niveauer:
| Porteføljeværdi | Max symboler | Aktivklasser |
|-----------------|-------------|--------------|
| < $2.000        | 3–5         | ETF'er kun (SPY, QQQ, GLD) |
| $2.000–$10.000  | 5–10        | ETF'er + krypto |
| $10.000–$50.000 | 10–20       | ETF'er + krypto + enkeltaktier |
| > $50.000       | 20+         | Fuld diversificering inkl. internationale |

Implementering:
- Porteføljestørrelse tjekkes automatisk ved hver rebalancering
- Watchlist udvides progressivt med forhåndsdefinerede symboler per niveau
- HRP-optimering sørger for at sprede inden for det aktive univers
- Notifikation sendes når et nyt niveau nås

---

## Prioritering (forslag)

1. **E-mail notifikationer + kill-switch** — høj prioritet, afgørende for unattended drift
2. **5-års simulering** — høj prioritet, nødvendig for tillid til systemet
3. **Intelligent positionsstørrelse** — medium, simpel at implementere
4. **Automatisk risikospredning ved vækst** — medium, bygger på eksisterende HRP
5. **Stress-test / markedssimulering** — lavere prioritet, nice-to-have

---

*Opdateret: 2026-03-15 — kill-switch præciseret*
