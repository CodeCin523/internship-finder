"""Default French templates, tailored to Dominic's internship search.

These are ordinary editable templates — change or delete them in the Templates
page. Placeholders ({company}, {contact_name}, {my_name}, {signature}) are filled
per company; the rest is written for a software-dev student seeking a Hiver 2027
stage, since these are personal starting points, not generic boilerplate.

`seed_templates` adds any default that isn't present (matched by name), so new
defaults appear on the next startup even on an existing database. A default you
delete will reappear on restart — tell me if you'd rather it stay deleted.
"""

from sqlmodel import Session, select

from app.models import Template, TemplateCategory

# --- first contact ---------------------------------------------------------

_SPONTANEE_DETAILLEE = """Madame, Monsieur,

Étudiant en Techniques de l'informatique (développement d'applications) au Collège Montmorency, je vous soumets ma candidature spontanée pour un stage en développement logiciel au sein de {company} pour la session d'hiver 2027.

Au fil de ma formation et de mes projets personnels, j'ai travaillé autant sur le développement web full-stack (JavaScript, Node.js, Express, bases de données) que sur des fondations systèmes en C. Cette double expérience m'a appris à comprendre un système à la fois dans sa structure et dans son usage concret.

Je suis disponible pour un stage de 10 semaines, à raison de 31,5 heures par semaine, à compter du 25 janvier 2027; ces modalités demeurent ajustables selon vos besoins. Vous trouverez ci-joint mon curriculum vitae, et mes projets sont disponibles sur GitHub (@CodeCin523).

Je serais ravi d'échanger avec vous et vous remercie de l'attention portée à ma candidature.

Cordialement,
{my_name}
{signature}"""

_SPONTANEE_COURTE = """Madame, Monsieur,

Étudiant en développement d'applications au Collège Montmorency, je recherche un stage en développement logiciel pour l'hiver 2027 et serais très intéressé à rejoindre {company}.

Mon profil couvre le développement web full-stack ainsi que la programmation système en C. Vous trouverez ci-joint mon curriculum vitae; je reste à votre disposition pour un échange.

Je vous remercie de votre attention.

Cordialement,
{my_name}
{signature}"""

_OFFRE_AFFICHEE = """Madame, Monsieur,

J'ai pris connaissance de votre offre de stage en développement logiciel et je souhaite y poser ma candidature. Étudiant en Techniques de l'informatique (développement d'applications) au Collège Montmorency, je crois que ce poste correspond à mon parcours et à mes intérêts.

J'ai développé des applications web full-stack (JavaScript, Node.js, Express, bases de données) ainsi que des projets systèmes en C, ce qui m'a permis de travailler sur différentes couches d'un logiciel, des données jusqu'à l'interface.

Je suis disponible pour un stage de 10 semaines, à 31,5 heures par semaine, à compter du 25 janvier 2027. Vous trouverez ci-joint mon curriculum vitae.

Je vous remercie de l'attention portée à ma candidature et reste disponible pour un entretien.

Cordialement,
{my_name}
{signature}"""

_PROFIL_WEB = """Madame, Monsieur,

Étudiant en développement d'applications au Collège Montmorency, je pose ma candidature pour un stage en développement web au sein de {company} pour l'hiver 2027.

J'ai conçu plusieurs applications full-stack avec JavaScript, Node.js, Express et des bases de données (MongoDB, MySQL). Avec QuillCC, une application de prise de notes structurées, j'ai notamment conçu une architecture permettant d'abstraire le stockage local et distant. J'aimerais approfondir le développement full-stack, l'intégration d'API et les bases de données dans un cadre professionnel.

Je suis disponible pour un stage de 10 semaines, à 31,5 heures par semaine, à compter du 25 janvier 2027. Mon curriculum vitae est joint, et mes projets sont sur GitHub (@CodeCin523).

Je vous remercie de votre attention.

Cordialement,
{my_name}
{signature}"""

_PROFIL_SYSTEMES = """Madame, Monsieur,

Étudiant en développement d'applications au Collège Montmorency, je pose ma candidature pour un stage en développement logiciel au sein de {company} pour l'hiver 2027, avec un intérêt particulier pour les aspects systèmes et bas niveau.

Mes projets personnels en C portent sur ces fondations : HARP, un runtime modulaire multiplateforme avec chargement dynamique de composants et remplacement à chaud, et Narthex, une bibliothèque de fondations système (allocateurs mémoire, gestion du cycle de vie). J'y ai développé une rigueur dans la structure, la gestion des dépendances et la détection de problèmes que je souhaite mettre au service de produits concrets.

Je suis disponible pour un stage de 10 semaines, à 31,5 heures par semaine, à compter du 25 janvier 2027. Mon curriculum vitae est joint; le code de mes projets est disponible sur GitHub (@CodeCin523).

Je vous remercie de l'attention portée à ma candidature.

Cordialement,
{my_name}
{signature}"""

_VIA_CONTACT = """Bonjour {contact_name},

Je me permets de vous écrire concernant un stage en développement logiciel au sein de {company} pour la session d'hiver 2027.

Étudiant en développement d'applications au Collège Montmorency, mon profil couvre le développement web full-stack ainsi que la programmation système en C. Je serais heureux de vous présenter mon parcours plus en détail et de discuter des possibilités de stage au sein de votre équipe.

Vous trouverez ci-joint mon curriculum vitae. Je vous remercie de votre temps.

Cordialement,
{my_name}
{signature}"""

# --- follow-up (relance) ---------------------------------------------------

_RELANCE_COURTE = """Madame, Monsieur,

Je me permets de revenir vers vous au sujet de ma candidature pour un stage en développement logiciel, envoyée récemment. N'ayant pas encore eu de retour, je tenais à réitérer mon intérêt pour {company} et reste à votre disposition pour tout échange.

Je vous remercie de votre attention.

Cordialement,
{my_name}
{signature}"""

_RELANCE_PORTFOLIO = """Madame, Monsieur,

Je me permets de faire un suivi concernant ma candidature de stage en développement logiciel au sein de {company}. Mon intérêt demeure entier, en particulier pour la possibilité de contribuer à des logiciels utilisés concrètement.

Si cela peut être utile, l'ensemble de mes projets (développement web et systèmes en C) est disponible sur GitHub (@CodeCin523). Je demeure disponible pour un stage à compter du 25 janvier 2027 et pour un entretien à votre convenance.

Je vous remercie et vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.

{my_name}
{signature}"""

_RELANCE_OFFRE = """Madame, Monsieur,

Je fais suite à ma candidature déposée pour votre offre de stage en développement logiciel. Souhaitant m'assurer de sa bonne réception, je me permets de vous relancer et de confirmer mon vif intérêt pour ce poste au sein de {company}.

Je reste disponible pour un entretien à votre convenance et vous remercie de votre attention.

Cordialement,
{my_name}
{signature}"""

# --- re-contact ------------------------------------------------------------

_MERCI_ENTREVUE = """Bonjour {contact_name},

Je vous remercie pour le temps que vous m'avez accordé lors de notre entretien concernant le stage en développement logiciel au sein de {company}. Notre échange a renforcé mon intérêt pour le poste et pour votre équipe.

Je reste à votre disposition pour toute information complémentaire et serais ravi de poursuivre le processus.

Cordialement,
{my_name}
{signature}"""

_SUIVI_ENTREVUE = """Bonjour {contact_name},

Je me permets de revenir vers vous à la suite de notre entretien concernant le stage en développement logiciel au sein de {company}. Je demeure très motivé à l'idée de rejoindre votre équipe et souhaitais savoir si vous disposiez de nouvelles quant à la suite du processus.

Je vous remercie et reste à votre entière disposition.

Cordialement,
{my_name}
{signature}"""

_REPONSE_REFUS = """Bonjour {contact_name},

Je vous remercie de m'avoir informé de votre décision et d'avoir pris le temps de considérer ma candidature. Bien que déçu, je comprends votre choix.

Je garde un bon souvenir de nos échanges et serais heureux de rester en contact pour d'éventuelles occasions futures au sein de {company}.

Je vous souhaite une excellente continuation.

Cordialement,
{my_name}
{signature}"""


DEFAULT_TEMPLATES = [
    {"name": "Candidature spontanée — détaillée", "category": TemplateCategory.first_contact,
     "language": "fr", "subject": "Candidature spontanée — stage en développement logiciel (hiver 2027)",
     "body": _SPONTANEE_DETAILLEE},
    {"name": "Candidature spontanée — courte", "category": TemplateCategory.first_contact,
     "language": "fr", "subject": "Candidature spontanée — stage en développement logiciel",
     "body": _SPONTANEE_COURTE},
    {"name": "Réponse à une offre affichée", "category": TemplateCategory.first_contact,
     "language": "fr", "subject": "Candidature — stage en développement logiciel chez {company}",
     "body": _OFFRE_AFFICHEE},
    {"name": "Candidature — profil web full-stack", "category": TemplateCategory.first_contact,
     "language": "fr", "subject": "Candidature — stage développement web chez {company}",
     "body": _PROFIL_WEB},
    {"name": "Candidature — profil systèmes (C/C++)", "category": TemplateCategory.first_contact,
     "language": "fr", "subject": "Candidature — stage développement logiciel (systèmes) chez {company}",
     "body": _PROFIL_SYSTEMES},
    {"name": "Prise de contact via une personne", "category": TemplateCategory.first_contact,
     "language": "fr", "subject": "Candidature — stage en développement logiciel",
     "body": _VIA_CONTACT},

    {"name": "Relance courte (sans réponse)", "category": TemplateCategory.follow_up,
     "language": "fr", "subject": "Relance : candidature de stage chez {company}",
     "body": _RELANCE_COURTE},
    {"name": "Relance — rappel d'intérêt + portfolio", "category": TemplateCategory.follow_up,
     "language": "fr", "subject": "Relance : ma candidature de stage chez {company}",
     "body": _RELANCE_PORTFOLIO},
    {"name": "Relance après offre affichée", "category": TemplateCategory.follow_up,
     "language": "fr", "subject": "Suivi : candidature à votre offre de stage",
     "body": _RELANCE_OFFRE},

    {"name": "Remerciement après entrevue", "category": TemplateCategory.re_contact,
     "language": "fr", "subject": "Merci pour notre entretien — {company}",
     "body": _MERCI_ENTREVUE},
    {"name": "Suivi après entrevue (sans nouvelles)", "category": TemplateCategory.re_contact,
     "language": "fr", "subject": "Suivi à la suite de notre entretien",
     "body": _SUIVI_ENTREVUE},
    {"name": "Réponse courtoise à un refus", "category": TemplateCategory.re_contact,
     "language": "fr", "subject": "Merci — {company}",
     "body": _REPONSE_REFUS},
]


def seed_templates(session: Session) -> None:
    """Add any default template not already present (matched by name)."""
    existing = {t.name for t in session.exec(select(Template)).all()}
    added = 0
    for data in DEFAULT_TEMPLATES:
        if data["name"] not in existing:
            session.add(Template(**data))
            added += 1
    if added:
        session.commit()
