"""
(C) legal_routes.py — Impressum, AGB, Datenschutz, Risikohinweis
"""

import os
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))


# --------------------------------------------------------------------------
# IMPRESSUM
# --------------------------------------------------------------------------

IMPRESSUM = """
<h2>Anbieter</h2>
<p>
  F&amp;S Coaching FZCO<br>
  Silicon Oasis, DDP, Building A1<br>
  Dubai, Vereinigte Arabische Emirate
</p>
<p><strong>Geschäftsführung:</strong> Maximilian Steinauer</p>
<p><strong>Kontakt:</strong><br>E-Mail: info@firstclass-trading.com</p>

<h2>Haftung für Inhalte</h2>
<p>Die Inhalte unserer Seiten wurden mit größter Sorgfalt erstellt. Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte können wir jedoch keine Gewähr übernehmen. Als Diensteanbieter sind wir gemäß § 7 Abs. 1 TMG für eigene Inhalte auf diesen Seiten nach den allgemeinen Gesetzen verantwortlich. Nach §§ 8 bis 10 TMG sind wir als Diensteanbieter jedoch nicht verpflichtet, übermittelte oder gespeicherte fremde Informationen zu überwachen oder nach Umständen zu forschen, die auf eine rechtswidrige Tätigkeit hinweisen.</p>
<p>Verpflichtungen zur Entfernung oder Sperrung der Nutzung von Informationen nach den allgemeinen Gesetzen bleiben hiervon unberührt. Eine diesbezügliche Haftung ist jedoch erst ab dem Zeitpunkt der Kenntnis einer konkreten Rechtsverletzung möglich. Bei Bekanntwerden von entsprechenden Rechtsverletzungen werden wir diese Inhalte umgehend entfernen.</p>

<h2>Haftung für Links</h2>
<p>Unser Angebot enthält Links zu externen Webseiten Dritter, auf deren Inhalte wir keinen Einfluss haben. Deshalb können wir für diese fremden Inhalte auch keine Gewähr übernehmen. Für die Inhalte der verlinkten Seiten ist stets der jeweilige Anbieter oder Betreiber der Seiten verantwortlich. Die verlinkten Seiten wurden zum Zeitpunkt der Verlinkung auf mögliche Rechtsverstöße überprüft. Rechtswidrige Inhalte waren zum Zeitpunkt der Verlinkung nicht erkennbar.</p>
<p>Eine permanente inhaltliche Kontrolle der verlinkten Seiten ist jedoch ohne konkrete Anhaltspunkte einer Rechtsverletzung nicht zumutbar. Bei Bekanntwerden von Rechtsverletzungen werden wir derartige Links umgehend entfernen.</p>

<h2>Urheberrecht</h2>
<p>Die durch die Seitenbetreiber erstellten Inhalte und Werke auf diesen Seiten unterliegen dem Urheberrecht. Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung außerhalb der Grenzen des Urheberrechtes bedürfen der schriftlichen Zustimmung des jeweiligen Autors bzw. Erstellers. Downloads und Kopien dieser Seite sind nur für den privaten, nicht kommerziellen Gebrauch gestattet.</p>
<p>Soweit die Inhalte auf dieser Seite nicht vom Betreiber erstellt wurden, werden die Urheberrechte Dritter beachtet. Insbesondere werden Inhalte Dritter als solche gekennzeichnet. Sollten Sie trotzdem auf eine Urheberrechtsverletzung aufmerksam werden, bitten wir um einen entsprechenden Hinweis. Bei Bekanntwerden von Rechtsverletzungen werden wir derartige Inhalte umgehend entfernen.</p>

<h2>Risikohinweis</h2>
<p>Der Handel mit Finanzinstrumenten wie Aktien, Futures, Optionen, Devisen (Forex) sowie insbesondere mit Hebelprodukten (z. B. CFDs) ist mit erheblichen Risiken verbunden und nicht für jeden Anleger geeignet. Es besteht die Möglichkeit, dass Sie einen Totalverlust des eingesetzten Kapitals erleiden oder sogar Verluste entstehen, die Ihre ursprüngliche Investition übersteigen. Nur Personen, die diese Risiken verstehen und finanziell in der Lage sind, erhebliche Verluste zu tragen, sollten sich an einem solchen Handel beteiligen.</p>
<p>FirstClass Trading richtet sich ausschließlich an Personen, die sich für Bildungs- und Informationszwecke interessieren. Sämtliche Inhalte auf dieser Website, in Schulungsmaterialien, Live-Calls, Communities und sonstigen Veröffentlichungen dienen ausschließlich der allgemeinen Information und Weiterbildung. Sie stellen ausdrücklich keine Finanz-, Anlage- oder Steuerberatung dar und sind auch keine Aufforderung oder Empfehlung zum Kauf, Verkauf oder Halten von Finanzinstrumenten.</p>
<p>Jede Handels- oder Anlageentscheidung wird eigenverantwortlich und auf eigenes Risiko getroffen. Wir übernehmen keinerlei Haftung für Verluste oder Schäden, die direkt oder indirekt aus der Nutzung oder dem Vertrauen auf bereitgestellte Informationen entstehen. Wir empfehlen, sich vor Aufnahme des Handels umfassend über die Risiken zu informieren und gegebenenfalls eine unabhängige fachliche Beratung in Anspruch zu nehmen.</p>

<h2>Streitbeilegung</h2>
<p>Die Europäische Kommission stellt eine Plattform zur Online-Streitbeilegung (OS) bereit: <a href="https://ec.europa.eu/consumers/odr/" target="_blank" rel="noopener">https://ec.europa.eu/consumers/odr/</a>. Wir sind nicht bereit oder verpflichtet, an Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.</p>

<h2>Geltungsbereich</h2>
<p>Dieses Impressum gilt für die Webseiten www.firstclass-trading.com, www.firstclass-trading.de sowie für alle zugehörigen Social-Media-Profile.</p>

<div class="legal-footer">© 2025 F&amp;S Coaching FZCO. Alle Rechte vorbehalten.</div>
"""


# --------------------------------------------------------------------------
# AGB
# --------------------------------------------------------------------------

AGB = """
<h2>§ 1 Geltungsbereich</h2>
<p>1.1 Diese AGB gelten für alle Verträge und Leistungen der F&amp;S Coaching FZCO, Silicon Oasis, DDP, Building A1, Dubai, Vereinigte Arabische Emirate (nachfolgend "Anbieter"). Sie regeln die Geschäftsbeziehung zwischen dem Anbieter und Verbrauchern bzw. Unternehmern in Bezug auf den Erwerb und die Nutzung der angebotenen Waren und Dienstleistungen.</p>
<p>Der Geltungsbereich umfasst insbesondere: Online-Coachings, Webinare, Seminare, Videokurse, Mitgliedschaften in Signalgruppen sowie individuelle Beratungsleistungen, die über die Plattformen www.firstclass-trading.com, www.firstclass-trading.de und verbundene Social-Media-Kanäle (Instagram, Facebook, YouTube, Telegram) angeboten werden.</p>
<p>1.2 Änderungen dieser Bedingungen werden dem Kunden schriftlich, per Fax oder per E-Mail mitgeteilt. Widerspricht der Kunde diesen Änderungen nicht innerhalb von vier Wochen nach Mitteilung, gelten die Änderungen als angenommen.</p>

<h2>§ 2 Vertragsschluss</h2>
<p>2.1 Die Darstellung der Produkte und Dienstleistungen stellt kein verbindliches Angebot dar. Erst die Bestellung des Kunden ist ein verbindliches Angebot (§ 145 BGB). Mit der Annahme dieses Angebots durch den Anbieter wird eine Bestellbestätigung per E-Mail versandt.</p>
<p>2.2 Nach erfolgreicher Bestellung erhält der Kunde eine Kaufbestätigungs-E-Mail mit allen relevanten Daten. Der Kunde ist verpflichtet sicherzustellen, dass die angegebene E-Mail-Adresse korrekt ist.</p>
<p>2.3 Während des Bestellvorgangs hat der Kunde die Möglichkeit, seine Eingaben zu korrigieren. Vor dem Abschluss erhält er eine Übersicht aller Bestellangaben zur Überprüfung.</p>
<p>2.4 Der Vertragsschluss erfolgt in deutscher Sprache.</p>
<p>2.5 Die Kontaktaufnahme durch den Anbieter erfolgt per E-Mail.</p>
<p>2.6 Bei digitalen Gütern gewährt der Anbieter ein nicht ausschließliches, räumlich und zeitlich unbegrenztes Recht zur Nutzung der Inhalte für private und geschäftliche Zwecke. Eine Weitergabe an Dritte oder eine Vervielfältigung für Dritte ist ohne ausdrückliche Genehmigung des Anbieters untersagt.</p>
<p>2.7 Der Kunde willigt ein, dass die vertragsbezogene Kommunikation in der Regel per E-Mail erfolgt — einschließlich Rechnungen, Vertragsänderungen und sonstigen Informationen.</p>

<h2>§ 3 Zahlungsbedingungen</h2>
<p>3.1 Der Kaufpreis ist mit Bestellung sofort fällig. Die Zahlung erfolgt über die zur Verfügung gestellten Zahlungsmethoden.</p>
<p>3.2 Es gelten die zum Zeitpunkt der Bestellung angegebenen Preise. Die ausgewiesenen Preise verstehen sich inklusive der gesetzlichen Mehrwertsteuer, sofern anwendbar.</p>
<p>3.3 Eine Aufrechnung gegen Forderungen des Anbieters ist nur mit unbestrittenen oder rechtskräftig festgestellten Gegenforderungen zulässig.</p>
<p>3.4 Die Abwicklung der Zahlungen erfolgt über den externen Zahlungsdienstleister Ablefy GmbH, Potsdamer Straße 125, 10783 Berlin, Deutschland. Ablefy übernimmt die Zahlungsabwicklung, Rechnungsstellung sowie das Abonnement-Management im Auftrag des Anbieters. Der Kaufvertrag besteht ausschließlich zwischen Kunde und Anbieter; die Zahlungsabwicklung erfolgt separat über Ablefy.</p>

<h2>§ 4 Versandbedingungen</h2>
<p>4.1 Der Versand der Waren erfolgt nach den getroffenen Vereinbarungen. Anfallende Versandkosten werden in der Produktbeschreibung ausgewiesen und auf der Rechnung gesondert aufgeführt.</p>
<p>4.2 Digitale Güter werden elektronisch entweder als Download oder per E-Mail bereitgestellt.</p>

<h2>§ 4a Umsatzsteuer und steuerrechtliche Hinweise</h2>
<p>4a.1 Der Anbieter hat seinen Sitz in den Vereinigten Arabischen Emiraten. Die angebotenen Leistungen umfassen individualisierte Dienstleistungen wie persönliche Betreuung, Live-Calls, Analysen und die Bereitstellung von Informationsmaterial — und stellen keine ausschließlich elektronisch erbrachten Dienstleistungen im Sinne der Mehrwertsteuer-Richtlinien dar. Aus diesem Grund wird die Mehrwertsteuer gemäß den geltenden Regelungen nicht ausgewiesen.</p>
<p>4a.2 Der Kunde ist selbst dafür verantwortlich, die in seinem Heimatland geltenden steuerrechtlichen Bestimmungen zu prüfen und etwaige steuerliche Pflichten ordnungsgemäß zu erfüllen. Der Anbieter schließt jegliche Haftung für die steuerrechtlichen Pflichten des Kunden ausdrücklich aus.</p>

<h2>§ 5 Widerrufsrecht</h2>
<p>5.1 Verbrauchern (gemäß § 13 BGB) steht grundsätzlich ein gesetzliches Widerrufsrecht zu. Unternehmern (gemäß § 14 BGB), die in Ausübung ihrer gewerblichen oder selbständigen Tätigkeit handeln, steht kein gesetzliches Widerrufsrecht zu. Die ausführliche Widerrufsbelehrung wird auf der Zahlungsseite des jeweiligen Produkts ausgewiesen.</p>
<p>5.2 Bei der Lieferung digitaler Inhalte (nicht auf einem körperlichen Datenträger) erlischt das Widerrufsrecht des Verbrauchers vorzeitig, wenn der Anbieter mit der Ausführung des Vertrages begonnen hat, nachdem der Verbraucher ausdrücklich zugestimmt hat, dass mit der Ausführung vor Ablauf der Widerrufsfrist begonnen werden soll, und bestätigt hat, dass er sein Widerrufsrecht durch diese Zustimmung verliert.</p>
<p>5.3 Dienstleistungsverträge haben eine vereinbarte Erstlaufzeit. Sofern nicht ausdrücklich anders vereinbart, verlängern sie sich nach Ablauf automatisch um die ursprüngliche Laufzeit, sofern keine der Vertragsparteien mit einer Frist von 14 Tagen vor Ende der Laufzeit schriftlich oder in Textform kündigt. Das Recht zur außerordentlichen Kündigung aus wichtigem Grund bleibt unberührt.</p>

<h2>§ 6 Offline-Events</h2>
<p>Beim Kauf von Tickets für Offline-Events gilt: Der Veranstalter behält sich das Recht vor, Veranstaltungen aus zwingenden organisatorischen oder wirtschaftlichen Gründen, die außerhalb seines Einflussbereichs liegen, abzusagen. Der Kunde wird in diesem Fall umgehend informiert, und die Tickets werden auf Folgeveranstaltungen umgebucht. Kosten, gegen die der Kunde sich hätte versichern können (Ticketversicherung, Reiserücktrittsversicherung etc.), werden nicht erstattet.</p>

<h2>§ 7 Gewährleistung</h2>
<p>Sofern die gelieferte Ware mangelhaft ist, kann der Kunde im Rahmen der gesetzlichen Bestimmungen Nacherfüllung, Rücktritt vom Vertrag bzw. Kündigung, Minderung, Schadensersatz oder den Ersatz vergeblicher Aufwendungen verlangen. Mängel, die dem Kunden vor dem Kauf bekannt waren, begründen keine Gewährleistungsansprüche. Gewährleistungsansprüche verjähren in zwei Jahren nach Erhalt der Ware.</p>

<h2>§ 8 Haftungsbeschränkung</h2>
<p>8.1 Der Anbieter haftet für Vorsatz und grobe Fahrlässigkeit. Darüber hinaus haftet der Anbieter für die fahrlässige Verletzung von Pflichten, deren Erfüllung die ordnungsgemäße Durchführung des Vertrags überhaupt erst ermöglicht, deren Verletzung die Erreichung des Vertragszwecks gefährdet und auf deren Einhaltung der Kunde regelmäßig vertrauen darf. Die Haftung ist jedoch auf den vorhersehbaren, vertragstypischen Schaden begrenzt.</p>
<p>8.2 Die vorstehenden Haftungsausschlüsse gelten nicht bei Verletzung von Leben, Körper und Gesundheit. Die Haftung nach dem Produkthaftungsgesetz bleibt unberührt.</p>
<p>8.3 Die Datenübertragung im Internet kann nach derzeitigem Stand der Technik nicht fehlerfrei und/oder dauerhaft verfügbar gewährleistet werden. Der Anbieter haftet daher nicht für die ständige und ununterbrochene Verfügbarkeit des Online-Systems und Online-Angebots.</p>

<h2>§ 9 Vertraulichkeit, Datenschutz und Teilunwirksamkeit</h2>
<p>9.1 Der Kunde verpflichtet sich, alle ihm im Rahmen der Zusammenarbeit mit dem Anbieter zugänglichen vertraulichen Informationen streng vertraulich zu behandeln und Dritten nicht zugänglich zu machen. Diese Verpflichtung besteht auch nach Vertragsende fort.</p>
<p>9.2 Der Anbieter verpflichtet sich, die gesetzlichen Datenschutzbestimmungen zu beachten und personenbezogene Daten des Kunden ausschließlich zur Vertragserfüllung und Pflege der Kundenbeziehung zu verwenden.</p>
<p>9.3 Sollten einzelne Bestimmungen dieser AGB ganz oder teilweise unwirksam sein oder werden, so bleibt die Wirksamkeit der übrigen Bestimmungen unberührt.</p>

<h2>§ 10 Erfolgsausschluss und Risikoübernahme</h2>
<p>10.1 Der Anbieter garantiert ausdrücklich keine bestimmten Erfolge. Sämtliche bereitgestellten Inhalte, Signale, Analysen, Marktkommentare und Empfehlungen dienen ausschließlich Informations- und Bildungszwecken und stellen keine individuelle Anlageberatung dar.</p>
<p>10.2 Auf der Website, in Social-Media-Kanälen und in Werbematerial dargestellte Ergebnisse basieren auf tatsächlichen Erfahrungen einzelner Mitglieder oder auf bereitgestellten Signalen. Sie dienen ausschließlich der Veranschaulichung und stellen keine Garantie für künftige Erfolge dar.</p>
<p>10.3 Der Kunde trifft alle Anlage- und Handelsentscheidungen eigenverantwortlich und auf eigenes Risiko. Der Anbieter schließt jegliche Haftung für Verluste oder Schäden, die aus den Handelsentscheidungen des Kunden resultieren, ausdrücklich aus.</p>
<p>10.4 Der Handel mit Finanzprodukten (Futures, Optionen, Devisen, Kryptowährungen) ist mit erheblichen Risiken verbunden, die zum Totalverlust des eingesetzten Kapitals führen können.</p>

<h2>§ 11 Urheberrecht und Vertragsstrafe</h2>
<p>11.1 Sämtliche vom Anbieter zur Verfügung gestellten Inhalte sind urheberrechtlich geschütztes geistiges Eigentum. Eine Vervielfältigung, Verbreitung, öffentliche Zugänglichmachung oder Weitergabe an Dritte ist ohne vorherige schriftliche Zustimmung untersagt.</p>
<p>11.2 Mit Vertragsschluss erhält der Kunde ein einfaches, nicht übertragbares und nicht unterlizenzierbares Nutzungsrecht zur ausschließlich persönlichen Nutzung.</p>
<p>11.3 Bei einer schuldhaften Zuwiderhandlung schuldet der Kunde eine Vertragsstrafe in Höhe des zwanzigfachen Kaufpreises des betroffenen Produkts. Weitergehende Schadensersatzansprüche bleiben unberührt.</p>

<h2>§ 12 Mitwirkungspflichten und Verhalten in der Community</h2>
<p>12.1 Der Kunde ist verpflichtet, alle für die ordnungsgemäße Durchführung des Vertrags erforderlichen Mitwirkungshandlungen rechtzeitig und vollständig zu erbringen.</p>
<p>12.2 Der Kunde verpflichtet sich zu einem respektvollen und sachlichen Verhalten innerhalb der Community. Bei schwerwiegenden oder wiederholten Verstößen kann der Anbieter den Kunden nach einmaliger Abmahnung vorübergehend oder dauerhaft von der Teilnahme ausschließen.</p>
<p>12.3 Die Weitergabe von Zugangsdaten oder bereitgestellten Inhalten an Dritte ist untersagt.</p>

<h2>§ 13 Verfügbarkeit und Wartungsarbeiten</h2>
<p>Der Anbieter ist bemüht, seine Dienste und Plattformen mit möglichst geringen Unterbrechungen zur Verfügung zu stellen. Aus Gründen der Wartung, Sicherheit oder Kapazität kann es jedoch zu kurzfristigen Störungen kommen. Dies stellt keinen Mangel dar.</p>

<h2>§ 14 Höhere Gewalt</h2>
<p>Ereignisse höherer Gewalt, die die Erfüllung des Vertrages erheblich erschweren oder unmöglich machen, berechtigen den Anbieter, die Erfüllung um die Dauer der Behinderung zuzüglich einer angemessenen Anlaufzeit hinauszuschieben.</p>

<h2>§ 15 Schlussbestimmungen</h2>
<p>15.1 Änderungen oder Ergänzungen dieser AGB bedürfen der Schriftform.</p>
<p>15.2 Es gilt das Recht der Bundesrepublik Deutschland unter Ausschluss des UN-Kaufrechts. Bei Verbrauchern bleiben zwingende Bestimmungen des Heimatlandes des Verbrauchers unberührt.</p>
<p>15.3 Sollten einzelne Bestimmungen dieses Vertrags unwirksam sein oder werden, so bleibt der Vertrag im Übrigen davon unberührt.</p>

<div class="legal-footer">© 2025 F&amp;S Coaching FZCO. Alle Rechte vorbehalten.</div>
"""


# --------------------------------------------------------------------------
# RISIKOHINWEIS
# --------------------------------------------------------------------------

RISIKOHINWEIS = """
<h2>1. Allgemeine Risiken des Handels</h2>
<p>Der Handel mit Finanzinstrumenten wie Aktien, Futures, Optionen, Devisen (Forex) sowie insbesondere mit Hebelprodukten (z. B. CFDs) ist mit erheblichen Risiken verbunden und nicht für jeden Anleger geeignet. Es besteht die Möglichkeit, dass Sie einen Totalverlust des eingesetzten Kapitals erleiden oder sogar Verluste entstehen, die Ihre ursprüngliche Investition übersteigen.</p>
<p>Nur Personen, die diese Risiken verstehen und finanziell in der Lage sind, erhebliche Verluste zu tragen, sollten sich an einem solchen Handel beteiligen.</p>

<h2>2. Keine Beratung oder Empfehlung</h2>
<p>FirstClass Trading richtet sich ausschließlich an Personen, die sich für Bildungs- und Informationszwecke interessieren. Sämtliche Inhalte auf dieser Website, in unseren Schulungsmaterialien, Live-Calls, Communities oder sonstigen Veröffentlichungen dienen ausschließlich der allgemeinen Information und Weiterbildung.</p>
<p>Sie stellen ausdrücklich keine Finanz-, Anlage- oder Steuerberatung dar und sind auch keine Aufforderung oder Empfehlung zum Kauf, Verkauf oder Halten von Finanzinstrumenten.</p>

<h2>3. Eigenverantwortlichkeit und Haftungsausschluss</h2>
<p>Jede Handels- oder Anlageentscheidung wird eigenverantwortlich und auf eigenes Risiko getroffen. Wir übernehmen keinerlei Haftung für Verluste oder Schäden, die direkt oder indirekt aus der Nutzung oder dem Vertrauen auf bereitgestellte Informationen entstehen.</p>
<p>Wir empfehlen, sich vor Aufnahme des Handels umfassend über die Risiken zu informieren und gegebenenfalls eine unabhängige fachliche Beratung in Anspruch zu nehmen.</p>

<h2>4. Weitere Risiken und technische Aspekte</h2>
<p>Über die genannten Marktrisiken hinaus können auch technische Störungen, Marktverwerfungen, der Ausfall von Hardware oder Software sowie Unterbrechungen der Internetverbindung den Handel und die Handelsergebnisse negativ beeinflussen. Auch unvorhersehbare Ereignisse und externe Einflüsse können sich auf Handelsentscheidungen auswirken.</p>

<h2>5. Besondere Risiken von Hebelprodukten und Marginhandel</h2>
<p>Beim Handel mit Futures, Optionen, CFDs und anderen Hebelprodukten ist das Risiko besonders hoch. Aufgrund des Hebeleffekts können sich Verluste überproportional verstärken und über das eingesetzte Kapital hinausgehen. Es besteht die Pflicht zur Nachschusszahlung oder zur Hinterlegung zusätzlicher Sicherheiten (Margin).</p>
<p>Wird die geforderte Margin nicht rechtzeitig erbracht, kann es zu einer automatischen Auflösung der Positionen kommen. Die daraus resultierenden Verluste tragen Sie als Nutzer in vollem Umfang.</p>

<h2>6. Keine Erfolgsgarantie</h2>
<p>Die auf unserer Website sowie in unseren Social-Media-Kanälen dargestellten Ergebnisse basieren auf tatsächlichen Erfahrungen unserer Mitglieder oder auf von uns bereitgestellten Signalen. Sie dienen ausschließlich der Veranschaulichung und stellen keine Garantie für zukünftige Ergebnisse dar.</p>
<p>Die durchschnittlichen Trefferquoten basieren auf vergangenen Erfahrungen, können stark schwanken und sind keine Grundlage für Erwartungen an zukünftige Ergebnisse.</p>

<h2>7. Ihre Bestätigung</h2>
<p>Mit der Nutzung dieser Website und unserer Dienste bestätigen Sie, dass Sie die Risiken des Handels mit Finanzinstrumenten verstanden haben und auf eigenes Risiko handeln. Eine Haftung von FirstClass Trading für direkte oder indirekte Verluste ist — soweit gesetzlich zulässig — ausgeschlossen. Sie tragen die volle Verantwortung für jede auf Basis der bereitgestellten Informationen getroffene Entscheidung.</p>

<p><strong>Kontakt:</strong> Bei Fragen zum Risikohinweis oder zu unseren Inhalten erreichen Sie uns unter: info@firstclass-trading.com</p>

<div class="legal-footer">© 2025 F&amp;S Coaching FZCO. Alle Rechte vorbehalten.</div>
"""


# --------------------------------------------------------------------------
# DATENSCHUTZ
# --------------------------------------------------------------------------

DATENSCHUTZ = """
<h2>1. Einleitung</h2>
<p>Wir, die F&amp;S Coaching FZCO, freuen uns über Ihren Besuch auf unserer Website und Ihr Interesse an unseren Angeboten. Der Schutz Ihrer personenbezogenen Daten hat für uns einen besonders hohen Stellenwert. Die Nutzung unserer Internetseiten ist grundsätzlich ohne jede Angabe personenbezogener Daten möglich. Sofern eine betroffene Person besondere Services unseres Unternehmens über unsere Internetseite in Anspruch nehmen möchte, könnte jedoch eine Verarbeitung personenbezogener Daten erforderlich werden.</p>
<p>Die Verarbeitung personenbezogener Daten erfolgt stets im Einklang mit der Datenschutz-Grundverordnung (DSGVO) und in Übereinstimmung mit den für unser Unternehmen geltenden landesspezifischen Datenschutzbestimmungen.</p>

<h2>2. Name und Anschrift des Verantwortlichen</h2>
<p>F&amp;S Coaching FZCO<br>Digital Park — Building A1<br>Dubai, Vereinigte Arabische Emirate<br>Tel.: +971 58 526 1945<br>E-Mail: info@firstclass-trading.com<br>Website: www.firstclass-trading.de</p>

<h2>3. Cookies</h2>
<p>Unsere Internetseite verwendet Cookies. Cookies sind Textdateien, die über einen Internetbrowser auf einem Computersystem abgelegt und gespeichert werden. Durch den Einsatz von Cookies können wir den Nutzern unserer Internetseite nutzerfreundlichere Services bereitstellen. Die betroffene Person kann die Setzung von Cookies jederzeit mittels einer entsprechenden Einstellung des Internetbrowsers verhindern.</p>

<h2>4. Erfassung von allgemeinen Daten und Informationen</h2>
<p>Unsere Internetseite erfasst mit jedem Aufruf eine Reihe von allgemeinen Daten und Informationen. Diese werden in den Logfiles des Servers gespeichert. Erfasst werden können: verwendete Browsertypen und Versionen, das vom zugreifenden System verwendete Betriebssystem, die Internetseite von welcher ein zugreifendes System auf unsere Internetseite gelangt (Referrer), die Unterseiten, Datum und Uhrzeit eines Zugriffs, eine Internet-Protokoll-Adresse (IP-Adresse) sowie der Internet-Service-Provider des zugreifenden Systems.</p>

<h2>5. Registrierung auf unserer Internetseite</h2>
<p>Die betroffene Person hat die Möglichkeit, sich auf der Internetseite unter Angabe von personenbezogenen Daten zu registrieren. Welche Daten dabei übermittelt werden, ergibt sich aus der jeweiligen Eingabemaske. Die eingegebenen Daten werden ausschließlich für die interne Verwendung erhoben und gespeichert.</p>

<h2>6. Kontaktmöglichkeit</h2>
<p>Unsere Internetseite enthält Angaben, die eine schnelle elektronische Kontaktaufnahme zu unserem Unternehmen ermöglichen. Sofern eine betroffene Person per E-Mail oder über ein Kontaktformular den Kontakt aufnimmt, werden die übermittelten personenbezogenen Daten automatisch gespeichert und ausschließlich für Zwecke der Bearbeitung verwendet.</p>

<h2>7. Routinemäßige Löschung und Sperrung von personenbezogenen Daten</h2>
<p>Wir verarbeiten und speichern personenbezogene Daten nur für den Zeitraum, der zur Erreichung des Speicherungszwecks erforderlich ist oder sofern dies gesetzlich vorgesehen wurde. Entfällt der Speicherungszweck oder läuft eine Speicherfrist ab, werden die Daten routinemäßig gesperrt oder gelöscht.</p>

<h2>8. Rechte der betroffenen Person</h2>
<ul>
  <li><strong>Recht auf Bestätigung</strong> — Jede betroffene Person hat das Recht, vom Verantwortlichen eine Bestätigung darüber zu verlangen, ob sie betreffende personenbezogene Daten verarbeitet werden.</li>
  <li><strong>Recht auf Auskunft</strong> — Jede betroffene Person hat das Recht, jederzeit unentgeltliche Auskunft über die gespeicherten Daten zu erhalten.</li>
  <li><strong>Recht auf Berichtigung</strong> — Jede betroffene Person hat das Recht, die unverzügliche Berichtigung unrichtiger Daten zu verlangen.</li>
  <li><strong>Recht auf Löschung</strong> — Jede betroffene Person hat das Recht, die Löschung sie betreffender Daten zu verlangen, sofern gesetzliche Gründe zutreffen.</li>
  <li><strong>Recht auf Einschränkung der Verarbeitung</strong> — Jede betroffene Person hat das Recht, die Einschränkung der Verarbeitung zu verlangen.</li>
  <li><strong>Recht auf Datenübertragbarkeit</strong> — Jede betroffene Person hat das Recht, ihre Daten in einem strukturierten, gängigen und maschinenlesbaren Format zu erhalten.</li>
  <li><strong>Recht auf Widerspruch</strong> — Jede betroffene Person hat das Recht, jederzeit Widerspruch gegen die Verarbeitung einzulegen. Dies gilt auch für Direktwerbung.</li>
  <li><strong>Recht auf Widerruf</strong> — Jede betroffene Person hat das Recht, eine Einwilligung zur Verarbeitung personenbezogener Daten jederzeit zu widerrufen.</li>
</ul>

<h2>9. Datenschutzbestimmungen zu eingesetzten Diensten</h2>
<p>Wir haben auf dieser Internetseite Komponenten von Facebook (Meta), Google Analytics, Google Ads, Instagram, YouTube und LinkedIn integriert. Details zu den jeweiligen Datenschutzbestimmungen finden Sie auf den Webseiten der Anbieter.</p>

<h2>10. Rechtsgrundlage der Verarbeitung</h2>
<p>Art. 6 Abs. 1 lit. a DSGVO dient als Rechtsgrundlage für Einwilligungen. Art. 6 Abs. 1 lit. b DSGVO für Vertragserfüllung. Art. 6 Abs. 1 lit. c DSGVO für rechtliche Verpflichtungen. Art. 6 Abs. 1 lit. f DSGVO für berechtigte Interessen.</p>

<h2>11. Dauer der Speicherung</h2>
<p>Das Kriterium für die Dauer der Speicherung ist die jeweilige gesetzliche Aufbewahrungsfrist. Nach Ablauf werden die Daten routinemäßig gelöscht, sofern sie nicht mehr zur Vertragserfüllung erforderlich sind.</p>

<p><strong>Kontakt zum Datenschutz:</strong> Bei Fragen zum Datenschutz oder zur Ausübung Ihrer Rechte: info@firstclass-trading.com</p>

<div class="legal-footer">© 2025 F&amp;S Coaching FZCO. Alle Rechte vorbehalten.</div>
"""


# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------

@router.get("/impressum")
async def impressum(request: Request):
    return templates.TemplateResponse(request, "legal.html", {
        "title": "Impressum", "content": IMPRESSUM,
    })

@router.get("/agb")
async def agb(request: Request):
    return templates.TemplateResponse(request, "legal.html", {
        "title": "Allgemeine Geschäftsbedingungen", "content": AGB,
    })

@router.get("/risikohinweis")
async def risikohinweis(request: Request):
    return templates.TemplateResponse(request, "legal.html", {
        "title": "Risikohinweis", "content": RISIKOHINWEIS,
    })

@router.get("/datenschutz")
async def datenschutz(request: Request):
    return templates.TemplateResponse(request, "legal.html", {
        "title": "Datenschutzerklärung", "content": DATENSCHUTZ,
    })
