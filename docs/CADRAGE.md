# Cadrage : Hockey Score Widget

Petit logiciel Windows pour un streamer fan de hockey (Canadiens de Montréal en priorité).
Il affiche le score d'un match NHL en direct dans OBS, sous forme de widget.

## Décisions déjà prises

- Logiciel séparé d'OBS-Dynamics, même stack pour réutiliser le savoir-faire :
  Python, `customtkinter` (interface), `simpleobsws` (OBS WebSocket v5), `pyinstaller` (exe).
- Source des scores : API publique NHL `https://api-web.nhle.com/v1/score/now`
  (gratuite, sans clé, non officielle). Testée le 2026-11-10 sur un match en direct.
- Pas de lecture d'écran (OCR) en version 1. Autres ligues : plus tard, si le streamer le demande.
- OnHockey (site de visionnage) n'a ni score ni API : inutile pour le widget.
- Le streamer regarde aussi sur RDS et TVA Sports, selon le diffuseur du match.
  Ce sont des matchs NHL : l'API NHL donne déjà leur score, rien à lire sur ces sites.
  Le retard du flux change d'un site à l'autre : le réglage « retard en secondes » doit être facile à ajuster.

## Forme du logiciel (exigence de l'utilisateur)

- Petit logiciel de bureau, comme OBS-Dynamics : une vraie fenêtre avec ses onglets.
- Jamais de fenêtre console noire : exe `pyinstaller --windowed`, lancement en dev par `pythonw`.
- Jamais de page à ouvrir dans Chrome : la page locale du widget sert seulement à la source navigateur d'OBS.

## Interface (exigence de l'utilisateur)

- Onglets dans une barre latérale à gauche, comme OBS-Dynamics (pas le `CTkTabview` en haut du lot 1 : à remplacer).
- Visuel soigné, au niveau d'OBS-Dynamics : s'inspirer de sa `Sidebar` et de son style.

## Couleurs

- Logiciel : vert de la chaîne Twitch du streamer, doux et frais, ni criard ni sombre.
  Vert principal `#2D7F55`, survol `#256B47` (texte blanc lisible, environ 5:1). Défini dans `hockey_widget/app.py`.
- Widget : maquette proposée par nous, détails à valider avec le streamer.

## Fonctionnement

1. L'application interroge l'API NHL toutes les 10 à 15 secondes pendant un match.
2. Un petit serveur HTTP local sert la page du widget (`http://127.0.0.1:<port>/widget`).
3. Dans OBS, une source navigateur affiche cette page. Le widget se met à jour en direct.
4. Via OBS WebSocket, l'application crée ou met à jour cette source navigateur toute seule.

## Onglet 1 : Aperçu

- Aperçu du widget tel qu'il apparaît dans OBS.
- Liste des matchs NHL du jour (heure, équipes, état : à venir, en direct, terminé).
- Mode auto : suit le match des Canadiens (`MTL`) quand ils jouent.
- Mode manuel : choisir n'importe quel match de la liste.
- État de connexion : API NHL, OBS WebSocket.

## Onglet 2 : Personnaliser

- Noms des équipes : par défaut, l'API les remplit toute seule (abréviation `MTL`,
  ou nom `Canadiens`). Champ pour forcer un nom à la main, avec bouton « revenir au nom de l'API ».
- Format du nom : abréviation, nom court, nom complet.
- Logos des équipes (fournis par l'API) : affichés ou masqués.
- Éléments affichés : score, période, chrono, tirs au but, état (avantage numérique, prolongation).
- Couleurs, police, taille, position, fond transparent ou opaque.
- Retard en secondes : décale l'affichage pour ne pas annoncer un but avant le flux vidéo.

## Onglet 3 : Réglages

- OBS WebSocket : adresse, port, mot de passe, bouton « tester la connexion ».
- Scène OBS où placer la source navigateur.
- Port du serveur local du widget.
- Fréquence d'interrogation de l'API.
- Langue de l'interface (français par défaut).
- Lancement au démarrage de Windows (option).

## Hors version 1

- Autres ligues (KHL, Ligue Magnus, Swiss League…) et lecture d'écran.
- Animations de but, son, alertes chat.
- Version macOS.

## Risques

- API NHL non officielle : elle peut changer sans prévenir. Code de lecture isolé dans un seul module.
- Limites de débit de l'API non documentées : rester à 10 secondes minimum entre deux appels.
- Mot de passe OBS WebSocket : stocké en local seulement, jamais dans le code ni dans les logs.

## Lots

1. Squelette : projet Python, tests, `.gitignore`, fenêtre à 3 onglets vides.
2. Lecture de l'API NHL : matchs du jour, score d'un match, tests sur réponses enregistrées.
3. Serveur local + page du widget, mise à jour en direct.
4. Onglet Aperçu : liste des matchs, mode auto Canadiens, mode manuel.
5. Onglet Réglages : connexion OBS WebSocket, création de la source navigateur.
6. Onglet Personnaliser : noms, couleurs, éléments affichés, retard.
7. Exécutable Windows avec `pyinstaller`.

## Questions ouvertes

- Projet perso ou distribué publiquement (licence, site, mises à jour) ?
- Nom du logiciel.
