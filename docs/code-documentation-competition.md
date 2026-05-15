# Dokumentacija koda za Glyco

## 1. Arhitektura sistema

Glyco je podijeljen u cetiri glavna sloja: React frontend, FastAPI backend, SQLite baza i ML pipeline. Frontend korisniku prikazuje dashboard, unos profila, monitoring logove, izvjestaje, family view i agent chat. Backend je centralni sloj koji prima podatke, cuva ih u bazi, poziva modele, generise objasnjenja i vraca strukturirane API odgovore. SQLite sluzi kao lokalna perzistencija za korisnike, profile, logove, procjene, izvjestaje, alerte i feedback agenta. ML sloj sadrzi skripte za pripremu podataka, treniranje modela i sacuvane artefakte.

Najvazniji backend tok pocinje u `app/api/routes.py`. Kada korisnik unese profil, backend racuna BMI, cuva profil i pokrece risk assessment. Kada korisnik unese novo ocitanje glukoze, backend automatski upisuje datum, cuva fasting/not fasting oznaku, pokrece monitoring assessment i zatim proactive check koji moze kreirati alert. Agent chat endpoint prima pitanje korisnika i poziva `agent_service.py`, gdje se orkestriraju svi alati potrebni za odgovor.

## 2. Backend i agent

Agent se nalazi u `backend/app/agent`. Modul `tools.py` definise alate koje agent koristi: ucitavanje profila, ucitavanje logova, pokretanje procjene rizika, pokretanje monitoring procjene i retrieval smjernica. Modul `safety.py` provjerava urgentne simptome prije generisanja odgovora. Modul `agent_service.py` spaja sve u jedan agentski tok: prvo ucitava kontekst korisnika, zatim cita memoriju iz feedback tabele, zatim poziva modele i smjernice, pa tek onda generise odgovor preko konfigurisanog LLM klijenta ili fallback logike.

Novi learning loop je implementiran preko tabele `agent_feedback`. Korisnik moze oznaciti da li je odgovor bio koristan, koji ton preferira i koju akciju potvrdjuje. Agent cita zadnjih 12 feedback zapisa i iz njih izracunava `learning_summary`: broj feedback signala, procenat korisnosti, preferirani ton, potvrdjene akcije, preferirani fokus preporuka, nedavni obrazac glukoze i next-best action. Taj summary se vraca frontend-u i koristi u narednom odgovoru. Time Glyco ima dokazivu online adaptaciju, a ne samo offline treniran model.

## 3. Masinsko ucenje i fallback

Risk model koristi BRFSS dataset i treniran je kao random forest classifier. Backend profil prevodi u isti feature oblik koji model ocekuje, zatim dobija vjerovatnocu i pretvara je u nivo rizika: low, medium ili high. Monitoring model koristi UCI time-series podatke, ali produkcijski feature contract je glucose-only da odgovara pojednostavljenom patient flow-u. Logovi se agregiraju u dnevne karakteristike kao sto su prosjecna glukoza, standardna devijacija, minimum, maksimum, broj visokih ocitanja, broj niskih ocitanja i kratkorocni trend.

Ako ML artefakti nisu dostupni ili korisnik nema dovoljno historije, backend ne pada. Risk procjena prelazi na deterministic rules fallback, a monitoring prelazi na engineered rules fallback. Ovo je bitno za usability i demo sigurnost: aplikacija ostaje funkcionalna i transparentno pokazuje koji model ili fallback je koristen.

## 4. Frontend interface

Frontend je React + Vite aplikacija. Agent ekran prikazuje chat, brzo dostupna pitanja, evidence panel sa tool calls, safety note, smjernice i novu Agent Memory karticu. Korisnik moze poslati feedback kroz Teach Glyco panel. Nakon toga naredni agent odgovor prikazuje da je feedback ucitan i koristi preferirani ton ili ranije potvrdjenu akciju.

Dashboard, Risk Check, Monitoring, Reports, Care Plan i Family View zajedno pokazuju primjenjivost agenta. Korisnik ne mora razumjeti ML modele: dobija objasnjenje rizika, trend, preporucene korake, izvjestaj za doktora i porodicni prikaz koji pojednostavljuje status.

## 5. Testiranje i ogranicenja

Backend testovi provjeravaju ucitavanje ML artefakata, high/low risk demo korisnike, monitoring model, fallback za nedovoljnu historiju, izvjestaje, agent tool calls, urgent safety odgovor, proactive alerts i novi feedback/memory tok. Ogranicenje sistema je da nije medicinski dijagnosticki alat. Modeli daju screening i monitoring podrsku, a ne klinicku odluku. Zato svaki odgovor sadrzi safety boundary i preporuku da se vazne odluke provjere sa kvalifikovanim zdravstvenim radnikom.

Reference:

1. Centers for Disease Control and Prevention, Behavioral Risk Factor Surveillance System.
2. UCI Machine Learning Repository, Diabetes Data Set.
3. American Diabetes Association, Standards of Care in Diabetes.
4. FastAPI Documentation.
