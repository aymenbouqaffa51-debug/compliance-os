# Module de clauses contractuelles types et analyse d'impact du transfert

**Objet :** permettre à un client établi dans l'Union européenne de transférer des données à caractère personnel vers {{PROVIDER_LEGAL_NAME}} (Maroc), en l'absence de décision d'adéquation de la Commission européenne couvrant le Maroc.

---

## Partie A — Constat de départ

**A.1** Le Maroc ne bénéficie d'**aucune décision d'adéquation** de la Commission européenne. La liste publiée par la Commission ne mentionne pas le Maroc.

**A.2** En conséquence, un exportateur établi dans l'Union européenne qui transfère des données à caractère personnel vers {{PROVIDER_LEGAL_NAME}} doit s'appuyer sur un mécanisme de l'article 46 du RGPD, en pratique des **clauses contractuelles types** complétées par une **analyse d'impact du transfert**.

**A.3** Cette analyse est distincte de la conformité marocaine. La loi 09-08 s'applique par ailleurs, et la CNDP exige ses propres formalités.

---

## Partie B — Clauses contractuelles types (module 2 : responsable vers sous-traitant)

Les parties déclarent incorporer par référence les **clauses contractuelles types** adoptées par la Commission européenne pour les transferts vers des sous-traitants établis dans un pays tiers, en complétant les annexes comme suit.

**Annexe I.A — Liste des parties**

| Rôle | Entité | Adresse | Contact |
|---|---|---|---|
| Exportateur (responsable) | {{EXPORTER_NAME}} | {{EXPORTER_ADDRESS}} | {{EXPORTER_CONTACT}} |
| Importateur (sous-traitant) | {{PROVIDER_LEGAL_NAME}} | {{PROVIDER_ADDRESS}} | {{PROVIDER_CONTACT}} |

**Annexe I.B — Description du transfert**

| Élément | Valeur |
|---|---|
| Catégories de personnes concernées | {{DATA_SUBJECTS}} |
| Catégories de données | {{DATA_CATEGORIES}} |
| Données sensibles | {{SENSITIVE_DATA}} |
| Fréquence du transfert | {{TRANSFER_FREQUENCY}} |
| Finalité | {{PURPOSE}} |
| Durée de conservation | {{RETENTION}} |
| Sous-traitants ultérieurs | {{SUBPROCESSORS_LIST}} |

**Annexe II — Mesures techniques et organisationnelles**

Voir l'annexe 2 de l'accord de sous-traitance (DPA) conclu entre les parties, qui est réputée incorporée.

**Annexe III — Sous-traitants ultérieurs**

{{SUBPROCESSORS_TABLE}}

---

## Partie C — Analyse d'impact du transfert (TIA)

### C.1 Nature et sensibilité des données

{{TIA_DATA_NATURE}}

### C.2 Législation et pratiques du pays de destination

**C.2.1** Le Maroc dispose d'une loi de protection des données (loi n° 09-08) et d'une autorité de contrôle indépendante (la CNDP), dotée de pouvoirs d'enquête et de sanction, dont les décisions peuvent faire l'objet de recours.

**C.2.2** La loi 09-08 impose des obligations de sécurité (articles 23 et 24), un secret professionnel sanctionné pénalement (article 26), et encadre les transferts vers l'étranger (articles 43 et 44).

**C.2.3** Les sanctions sont pénales et **doublées pour les personnes morales** (article 64), avec possibilité de fermeture de l'établissement.

**C.2.4** *Point d'attention :* la loi 09-08 **ne prévoit aucune obligation de notification des violations de données**. Une obligation contractuelle de notification a été consentie à l'annexe 1 de l'accord de sous-traitance.

**C.2.5** *Point d'attention :* l'accès par des autorités publiques marocaines à des données détenues par le sous-traitant n'est pas encadré par une disposition spécifique équivalente au chapitre V du RGPD. Les parties conviennent que le sous-traitant notifiera à l'exportateur toute demande d'accès d'une autorité, sauf interdiction légale, et contestera les demandes manifestement excessives.

### C.3 Mesures supplémentaires

| Mesure | Mise en oeuvre |
|---|---|
| Chiffrement en transit | TLS 1.2 minimum, TLS 1.3 recommandé |
| Chiffrement au repos | Actif sur l'ensemble des supports de stockage |
| Pseudonymisation / minimisation | Conservation d'empreintes et métadonnées plutôt que du document brut lorsque la finalité le permet |
| Accès | Moindre privilège, MFA, revue périodique |
| Journalisation | Accès journalisés, conservation 12 mois |
| Notification | Incident notifié à l'exportateur sous 48 heures |
| Localisation | Hébergement en **{{HOSTING_REGION}}** |
| Réversibilité | Restitution ou suppression certifiée sous 30 jours |
| Sous-traitance ultérieure | Préavis de 30 jours, droit d'opposition |

### C.4 Conclusion

{{TIA_CONCLUSION}}

---

## Partie D — Ce que ce document ne fait pas

Ce document est un **modèle opérationnel**, non un avis juridique. Il ne remplace pas :

- l'analyse de l'exportateur sur la nécessité du transfert ;
- la vérification que les clauses contractuelles types en vigueur sont correctement incorporées ;
- les formalités CNDP côté marocain (déclaration ou autorisation du traitement sous-jacent, puis autorisation de transfert le cas échéant).

**Fait le {{SIGNATURE_DATE}}**
