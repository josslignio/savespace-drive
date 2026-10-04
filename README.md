# SaveSpace Drive

Retrouve de la place sur ton ordinateur : doublons, gros fichiers et caches repérés en quelques
secondes, rangés en un clic, annulables à tout moment. 100 % local, gratuit, open source (MIT).
Aucune donnée ne quitte ta machine.

![Résultat d'une analyse](docs/captures/3_resultat.png)

## Installer (rien n'est payant)
L'app n'est pas signée par un certificat payant : c'est un choix, tout est gratuit.

**Mac — au choix :**
- **Terminal, sans aucun avertissement** (copie l'app dans Applications, ne laisse rien d'autre) :
  ```sh
  curl -fsSL https://raw.githubusercontent.com/josslignio/savespace-drive/main/install.sh | sh
  ```
- **Le fichier .dmg** (page [Releases](https://github.com/josslignio/savespace-drive/releases)) : l'ouvrir,
  glisser SaveSpace Drive sur Applications, l'ouvrir. macOS dit « Apple ne peut pas vérifier… » →
  **Terminé**. Puis **Réglages Système → Confidentialité et sécurité** → tout en bas,
  **Ouvrir quand même** → confirmer. Une seule fois.

**Windows :** le `.exe` de la page Releases. Windows affiche une fois « Windows a protégé votre
ordinateur » → **Informations complémentaires** → **Exécuter quand même**. Une version Microsoft Store
(sans aucun avertissement) est prévue. La version Windows est encore peu testée : signale tout souci
dans les Issues.

## Utiliser
1. Choisis un dossier (Téléchargements, Bureau, Documents, Vidéos ou un autre).
2. **Analyser** : rien n'est touché, tu vois ce que tu peux récupérer.
3. **Ranger les doublons** : la liste exacte des fichiers s'affiche d'abord ; rien ne bouge sans ton
   « Oui ». On garde l'original (pas « Copie de… » ni « (1) »), les copies vont dans un dossier
   `quarantaine`.
4. **Annuler / restaurer** remet tout en place, à l'identique (chaque fichier vérifié par empreinte).

## Limites, en clair
- La quarantaine reste sur le même disque : la place n'est libérée que quand tu la vides toi-même.
- Les gros fichiers et les caches sont montrés, jamais supprimés : à toi de décider.
- Le dossier personnel entier et la racine du disque sont refusés (trop risqué en un clic).
- En ligne de commande, `doublons` garde encore le premier nom par ordre alphabétique (l'app, elle,
  garde l'original).

## Ligne de commande (pour les curieux)
```sh
pipx install git+https://github.com/josslignio/savespace-drive
savespace-drive analyse --racine ~/Downloads
```
Commandes : `analyse` (à blanc), `doublons`, `gros`, `caches`, `restaure`, `doctor` (moteurs
optionnels : czkawka, rclone, osxphotos, dua). Ajoute `--json` pour une sortie machine.

## Crédits
Moteurs optionnels pris tels quels, tous libres : czkawka, rclone, osxphotos, dua/gdu ; emplacements de
caches repris de mac-cleaner-cli ; fenêtre par pywebview ; paquet par PyInstaller. Merci à leurs auteurs
(voir `THIRD_PARTY/`).

---

## English
**SaveSpace Drive** finds duplicates, big files and caches, and tidies duplicates away in one click —
always undoable, 100 % local, free and open source (MIT). Install: the one-line Terminal command or the
`.dmg` above (Mac, unsigned: *System Settings → Privacy & Security → Open Anyway* once), or the `.exe`
(Windows: *More info → Run anyway* once). Duplicates go to a `quarantaine` folder, never deleted;
*Annuler / restaurer* puts everything back.
