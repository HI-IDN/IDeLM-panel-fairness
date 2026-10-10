# Verklag Rannís við röðun fagráðsfunda: gögn úr tölvupóstsamskiptum

**Tilgangur.** Þetta skjal skráir hvernig starfsfólk Rannís raðar umsóknum á fagráðsfundi Tækniþróunarsjóðs í dag og hvað það vill sjá í lausn. Heimild er tölvupóstskipti Helgu Ingimundardóttur (HÍ) og sérfræðings hjá Rannís 1.–9. október 2026. Öll nöfn annarra, netföng, símanúmer, heimilisföng, umsóknarnúmer og heiti umsókna eru fjarlægð. Umsóknir og fagráðsmenn í tilvitnaða textanum eru sýnd með staðgenglum.

## 1. Helstu atriði

* **Núverandi aðferð er einfalt gervigreindarprompt** (spjallmenni), notað af starfsmanni fyrir fagráðsfundi í Sprota. Röðun innan fundar er ekki bestuð með reiknilíkani.
* **Tímaforsendur:** um 10 mín. á umsókn í Sprota, nær 15 mín. í Vexti. Starfsmaður hefur notað „aðeins frábrugðna skipan" fyrir fundi í Vexti.
* **Fjöldaskorður:** enginn fagráðsmaður má vera með fleiri en 4 umsóknir á fundi. Eitt tilvik með 6 umsóknum kom upp þegar annar fagráðsmaður boðaði forföll með stuttum fyrirvara á síðasta fundi og átti að vera með fjórar fyrstu umsóknirnar; þær voru fluttar með einfaldri handvirkri hrókeringu milli funda og viðkomandi var meðvitaður um það og samþykkti. Starfsmaður er sammála því að fleiri en fjórar umsóknir á mann séu óásættanlegar.
* **Séróskir fagráðsmanna** (utan prompts, send sem „aukaskilyrði"): geta ekki mætt á alla fundi, vilja vera framarlega í röðinni, vilja vera búnir fyrir tiltekinn tíma, mæta seint.
* **Dagskráin er flöktandi.** Oft kemur fram með stuttum fyrirvara að lesari geti ekki mætt eða hafi takmarkaðan tíma á fundi, að í ljós komi vanhæfi og skipta þurfi um lesara, og fleira af því tagi.
* **Keðjuáhrif:** þegar umsókn er flutt á annan fund eða skilyrðum eins lesara er breytt, hefur það áhrif á tvo aðra lesara á umsókninni, og skilyrði þeirra geta stangast á. Að finna nýjan fundartíma fyrir umsókn er sjálfstætt vandamál, því athuga þarf samræmi við skilyrði á hinum fundinum. Starfsmaður nefnir þetta sem úrlausnarefni fyrir framtíðarlausn sem gerir ráð fyrir flökti og „lifandi" dagskrá.
* **Birt dagskrá er erfitt að breyta.** Lesarar hafa gert ráðstafanir út frá auglýstri viðveru, og því þykir starfsfólki erfitt að breyta röðun haustfunda eftir útgáfu. Nýtt verklag á fremur að taka gildi síðar og vera innleitt markvisst, t.d. með námsmannaverkefni.
* **Áhugi á samanburði nálgana:** starfsfólk vill bera saman aðferðir (þar á meðal aðferð sem annar rannsakandi hefur þróað fyrir sjóðinn) og skoða á akademískum nótum.
* **Hugmynd að sviðsmynd 2 frá starfsmanni:** næsti fundur haldist óbreyttur, en gerður sé nákvæmari samanburður á núverandi áætlun og nýjum tillögum til að sjá hvað breytingin þýðir fyrir einstaka lesara.
* **Sviðsmynd 1:** að mati Helgu vill Rannís fara leið þar sem besta lausn er fundin miðað við þegar auglýsta áætlun.

## 2. Prompt starfsmanns (orðrétt, með staðgenglum)

Staðgenglar: umsóknir A1–A4; fagráðsmenn R1–R9. Textinn er að öðru leyti óbreyttur.

```text
You are to create a meeting schedule.
Each application takes 10 minutes to discuss.
The meeting starts at 16:00.

Applications (ID: Reviewers)
A1: R1 – R2 – R3
A2: R4 – R5 – R1
A3: R6 – R7 – R8
A4: R3 – R9 – R4

Constraints

* R1 cannot attend before 17:00.
* R6 must leave by 18:00.
* R3 should be scheduled as early as possible.

Reviewer availability optimization:
First satisfy all explicit scheduling constraints. Treat these as mandatory.
For each reviewer, define:

* Total idle length: The number of applications between their first and last assigned applications in which they do not participate. Do not count applications before their first participation or after their last.
* An idle gap: A consecutive sequence of applications between two of their appearances in which they do not participate.
* Gap length: The number of applications in that sequence.

Among schedules satisfying all mandatory constraints, optimize these objectives in the following priority order:

1. Minimize the sum of total idle lengths across all reviewers.
2. Among schedules tied on that measure, minimize the longest individual idle gap.
3. Among schedules still tied, minimize the total number of idle gaps.
4. Prefer consecutive applications involving recurring reviewer combinations.

Place reviewers appearing only once as early as possible without worsening the higher-priority objectives.
After the schedule, include a reviewer summary showing each reviewer's application count, first and last positions, total idle length, number of idle gaps, and longest gap.
State whether optimality was mathematically verified or whether the result is the best schedule found.

Output format: Produce a list in chronological order. Each line must include: [Ordinal number] [Start time – End time] | (Application ID) | Reviewers
Ensure all constraints are satisfied.
After the schedule, write a Confirmation of Constraints section formatted as follows:

* Use clear English sentences.
* Each constraint should be followed by a checkmark (✔️) if fulfilled, or a warning (⚠️) if not.
* Include brief notes in parentheses showing relevant times or applications.

If any constraint cannot be met, mark it with ⚠️ and clearly state the conflicting application IDs and times.
```

## 3. Athugasemdir um promptið

* Markmið promptsins er að lágmarka **bið** (óvirkar umsóknir milli fyrstu og síðustu umsóknar hvers lesara) innan eins fundar; það nær hvorki til **vals á fundi** fyrir umsókn né til **hlutverkaskiptingar** (ritstjóri, 1. og 2. lesari).
* Það hefur ekki skilgreint sanngirni milli fagráðsmanna á heilu fundaröðinni (fjöldi funda, samanlögð bið).
* Promptið biður gervigreindina sjálfa að „sannreyna" hagkvæmni; slík sannreyning er óáreiðanleg án reiknilíkans.
* Skorður í prompt (komutími, brottfarartími, „sem fyrst") samsvara að hluta tímagluggum og forgangi í líkaninu. Þær eru handskráðar fyrir hvern fund.

## 4. Tímalína samskipta (án nafna)

| Dags. | Atvik |
|---|---|
| 1. okt. 2026 | Starfsmaður tilkynnir Helgu um breytingu á lesara vegna vanhæfis; Helga er sett í staðinn á eina umsókn til viðbótar á fundi þar sem hún er þegar með tvær. Helga samþykkir og nefnir sambærilegt bestunarverkefni og sanngirni í fundasókn (þrír fagráðsmenn sitja alla 9 fundina en flestir 6). |
| 1. okt. 2026 | Starfsmaður lýsir áhuga; röðun var gerð með „einföldu prompti"; auka skilyrði um séróskir eru til. Nefnir að annar rannsakandi hafi boðið fram bestunaraðstoð. |
| 1. okt. 2026 | Helga bendir á að gervigreindarlíkan (LLM) sé ekki vel til þess fallið, spyr um hvort tekið sé tillit til endurinnsendra umsókna, og biður um söguleg gögn (breytingasaga í grunni, tímastimplar samþykktar umsókna) til að meta lausnir. |
| 2. okt. 2026 | Starfsmaður sendir yfirlit aukaskilyrða. |
| 5. okt. 2026 | Helga sendir fundaáætlun fyrir haustið (M1–M9) og óskar eftir fundi. |
| 9. okt. 2026 | Starfsmenn eru spenntir fyrir samstarfinu; vilja funda innbyrðis fyrst og bjóða hinum rannsakandanum með. Starfsmaður nefnir flökt í dagskrá og sviðsmynd 2 (sjá lið 1). |

## 5. Hvað þetta gefur til kynna um óskir Rannís

1. Lausn sem virðir **þegar auglýsta dagskrá** (sviðsmynd 1 í greinargerð) er raunhæfasti upphafspunktur.
2. Lausn þarf að ráða við **skorður einstakra lesara** og **breytingar með stuttum fyrirvara**, helst með endurkeyrslu og lágmarks röskun.
3. Samanburður **á einstökum lesurum** (hver græðir/tapar) skiptir máli, ekki aðeins heildarmælikvarðar.
4. Áhugi á **innleiðingu í verklag** sjóðsins, t.d. í gegnum námsmannaverkefni.

## 6. Hvað var sleppt

Nöfn og netföng allra annarra en Helgu, símanúmer, heimilisföng, umsóknarnúmer, heiti umsókna, tengla, fundardagsetningu tiltekins fundar, og fjármála- og launaumræðu um námsmannaverkefni (NSN).
