# Opis agenta Glyco

Glyco je personalizovani zdravstveni agent za podrsku osobama koje prate rizik i tok dijabetesa tipa 2. Njegova jedinstvenost je u tome sto nije samo chatbot: agent objedinjuje ML procjenu rizika, ML procjenu monitoring trenda, sigurnosna pravila, smjernice, proaktivne alerte, izvjestaje za doktora i pojednostavljeni porodicni prikaz. Korisnik dobija odgovor na prirodnom jeziku, ali iza odgovora stoji vise alata: ucitavanje profila, analiza zadnjih logova, pokretanje risk modela, pokretanje trend modela, retrieval smjernica i citanje personalizovane memorije.

Primjena agenta je prakticna: korisnik unosi jednostavno ocitanje glukoze i oznacava da li je fasting ili not fasting; Glyco zatim objasnjava sta se promijenilo, zasto je vazno, sta uraditi ove sedmice i sta pitati doktora. Sistem ne postavlja dijagnozu i ne zamjenjuje ljekara. Njegova vrijednost je u pripremi korisnika za razgovor sa zdravstvenim radnikom, ranom uocavanju obrazaca i boljem ukljucivanju porodice u podrsku.

Glyco uci na dva nivoa. Prvi nivo je offline masinsko ucenje: model rizika je treniran na CDC BRFSS datasetu, a model glucose-trenda na UCI diabetes time-series arhivi sa glucose-only feature contractom. Ti modeli uce opste obrasce populacijskog rizika i promjene glikemijskih trendova. Drugi nivo je online adaptacija agenta: korisnik moze ocijeniti odgovor, izabrati preferirani ton i potvrditi akciju. Agent iz feedbacka uci preferirani fokus preporuka, prepoznaje nedavne obrasce glukoze i bira adaptivni next-best action za naredni odgovor.

Za takmicenje se Glyco moze demonstrirati kroz kompletan tok: profil korisnika, risk assessment, unos novog loga, promjena monitoring trenda, agent odgovor, feedback korisnika, personalizovan naredni odgovor i generisanje izvjestaja za doktora ili porodicu.

Reference:

1. Centers for Disease Control and Prevention, Behavioral Risk Factor Surveillance System.
2. UCI Machine Learning Repository, Diabetes Data Set.
3. American Diabetes Association, Standards of Care in Diabetes.
4. World Health Organization, Diabetes fact sheet and digital health guidance.
