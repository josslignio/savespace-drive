# Ranger un drive en dossiers : la méthode (apprise du rangement fait à la main, 29-30/09/2026)

**D'où ça vient.** Le propriétaire a rangé à la main un Google Drive (racine de ~190 éléments en vrac, puis
plusieurs centaines de fichiers en vrac dans les dossiers : 421 comptés au tour 7) et un pCloud (~51 000 fichiers,
39 dossiers en haut). Sources relues pour écrire cette page : les consignes et les 11 « tours » de rapport du rangement Drive, les scripts de rangement pCloud
(`ranger.py`, `ranger2.py`, `plan_vrac.py`, `tri_moves.sh`), `prototype/vers_pcloud.sh` et `docs/STRATEGY.md` du dépôt
source, les transcriptions de ces deux jours, et une **liste en lecture seule** des dossiers du Google Drive (2 niveaux,
05/10). La liste de pCloud n'a pas pu être relue : l'accès a été retiré côté pCloud (« Revoked access_token »). L'arbre
pCloud ci-dessous vient donc des sorties de vérification enregistrées le 29/09. Seule la **forme** est reprise ici,
avec des exemples neutres, jamais un nom de fichier personnel.

## Le résultat obtenu à la main
**Google Drive : rangé par domaine de vie.** 10 dossiers en haut, numérotés, aucun fichier isolé :
`00 - ADMINISTRATIF & JURIDIQUE`, `01 - SOCIÉTÉS & PROJETS`, `02 - CLIENTS & PROPOSITIONS`, `03 - FACTURES & ABONNEMENTS`,
`04 - PERSO & PHOTOS`, `05 - VIDÉOS`, `06 - VOYAGES`, `07 - FORMATION & DOCS`, `08 - ARCHIVES`, plus un dossier gardé à
part (copie de pièce d'identité). Un niveau plus bas :
- administratif **par thème** : Impôts et aides, Banque, Santé, Identité, Emploi, Logement, Contrats et assurances ;
- sociétés et projets : **un sous-dossier par projet** ;
- clients : **un sous-dossier par client qui a au moins 3 fichiers**, les autres ensemble dans « Autres clients » ;
- factures : **par fournisseur ou par année** (exemple : « Autres 2024 ») ;
- photos : par événement ou lieu, sinon « Images diverses » ; vidéos : par thème ou par année ;
- voyages : un sous-dossier par voyage ; formation : par thème ;
- archives : **par année** (2012, 2020 à 2026), seulement pour les vieux fichiers sans catégorie claire.

**pCloud : rangé par type de contenu.** En haut : `DOCUMENTS`, `GRAPHISME`, `LOGICIELS`, `MUSIQUE`, `PHOTOS & VIDÉOS`,
plus les sauvegardes, **jamais touchées**. Dans les gros dossiers, des sous-dossiers numérotés avec thème et années,
par exemple `01 - Voyage en Asie (2017-2020)` ou `04 - Soirées & festivals (2018-2023)`. Mesure finale : 0 fichier à la
racine, 2 dossiers « mixtes » restants (des fichiers posés à côté de sous-dossiers).

## Les règles (celles que l'app applique)
1. **Une dizaine de dossiers en haut, au plus**, aux noms français lisibles, numérotés `01 - …` pour garder l'ordre.
   Deux thèmes voisins partagent un dossier (`FACTURES & ABONNEMENTS`).
2. **Aucun fichier en vrac** : ni en haut, ni directement dans un dossier du haut. Chaque fichier a un sous-dossier :
   thème pour l'administratif, **année** pour le reste, type pour les logiciels (« Installateurs », « Fichiers compressés »).
3. **Un ancien dossier se déplace tel quel**, avec son nom et son contenu, dans la catégorie de la plupart de ses
   fichiers, ou dans celle que dit son nom (`Impôts 2023` va dans l'administratif).
4. **On suit les dossiers déjà là.** Un dossier `Photos`, ou un dossier numéroté comme `04 - PERSO & PHOTOS`, sert de
   catégorie : rien n'est dédoublé. Un lieu déjà rangé n'a rien à bouger, et les nouvelles catégories prennent les
   numéros suivants.
5. **Jamais d'écrasement.** Si un nom est pris, on ajoute ` (2)`. C'était déjà le cas à la main sur pCloud
   (`--ignore-existing`, « REFUS destination existe »).
6. **Rien n'est effacé.** À la main, les dossiers vidés et la corbeille avaient été supprimés. L'app, elle, ne supprime
   rien : un dossier vide reste à sa place.
7. **Ce qu'on ne touche jamais** : les sauvegardes (exclues du rangement pCloud), Google Photos, les dossiers d'apps,
   les éléments partagés par d'autres (à la main, Drive refusait de les déplacer), les fichiers seulement dans iCloud,
   les fichiers cachés, les paquets macOS (photothèque, applications), les dossiers sensibles (`.git`, `.ssh`), et deux
   éléments au même nom au même endroit.
8. **Dans le doute, on ne déplace pas.** C'était la règle des consignes à la main (« dans le doute, garder les deux ») :
   un élément en conflit est laissé en place et listé.
9. **On ne croit aucun déplacement sur parole.** À la main, des déplacements « faits » ne l'étaient pas (Drive les
   annulait sans rien dire). L'app vérifie chaque déplacement sur place, et le note dans un journal **avant** de le
   faire. Un script à la main avait aussi créé un dossier au nom abîmé (`\u00c9crits…` à côté de `Écrits…`, mesuré dans la liste du 05/10) : l'app
   écrit les noms tels quels.
10. **Côté serveur seulement.** À la main : `rclone moveto` et `rclone move`, sans rien télécharger. L'app exige que
    le service sache déplacer lui-même, et interdit tout transfert (`--max-transfer 1B`).

## Ce que l'app ne sait pas faire comme le propriétaire
Elle ne lit pas le contenu des fichiers. Elle ne peut donc pas deviner un client, un projet ou un voyage : ces dossiers,
il les avait créés en regardant. Elle range par nom (mots-clés comme facture, impôts, contrat, CV, passeport, capture
d'écran…), par type et par année, et garde tels quels les dossiers qui existent déjà. Avant de dire oui, on peut
renommer un dossier proposé, le fusionner avec un autre ou l'exclure.

## Exemple (noms neutres)
```
En vrac : Facture électricité mars.pdf · CV 2024.pdf · IMG_0412.jpg · Vacances Rome/ · Impôts 2023/ · Installer Zoom.pkg
Après :   01 - ADMINISTRATIF/Emploi/CV 2024.pdf
          01 - ADMINISTRATIF/Impôts 2023/            (dossier déplacé tel quel)
          02 - FACTURES & ABONNEMENTS/2024/Facture électricité mars.pdf
          03 - PHOTOS & IMAGES/2024/IMG_0412.jpg
          03 - PHOTOS & IMAGES/Vacances Rome/         (la plupart de ses fichiers sont des photos)
          04 - LOGICIELS & COMPRESSÉS/Installateurs/Installer Zoom.pkg
```
