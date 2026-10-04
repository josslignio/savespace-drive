# Essayer les drives sur tes vrais comptes (lecture seule d'abord)

1. Quitte l'ancienne SaveSpace Drive si elle est ouverte, puis ouvre la nouvelle (version de la branche `drives`).
2. **iCloud Drive** : clique « iCloud Drive » puis **Analyser**. C'est une lecture seule. En bas s'affiche
   « N fichiers sont seulement dans iCloud : ignorés, rien n'a été téléchargé ». Vérifie que l'espace libre du Mac
   n'a pas baissé. **Ne clique pas sur « Ranger »** pendant ce premier essai.
3. **Google Drive** : clique « Google Drive », puis **Connecter Google Drive**. Ton navigateur s'ouvre sur la page
   de Google. Elle parle de « rclone » : c'est le moteur gratuit inclus dans l'app, c'est normal. Accepte, puis
   reviens dans l'app.
4. Clique **Analyser**. Seule la liste des fichiers est lue, rien n'est téléchargé. Note les chiffres : « Espace
   utilisé X sur Y », la place récupérable, la corbeille, Photos et Gmail. Compare « Espace utilisé » avec
   https://one.google.com/storage : ce doit être le même ordre de grandeur.
5. Ouvre « Voir la liste » des doublons et vérifie 2 ou 3 paires sur drive.google.com. Ce sont bien les mêmes
   fichiers, et celui qu'on garde est le bon.
6. Seulement ensuite, si tu veux : **Mettre les doublons à la corbeille…**. La liste exacte s'affiche.
   Commence par un petit essai (réponds « Annuler » si la liste est longue). Après « Oui », ouvre la corbeille
   avec le lien affiché et restaure un fichier, pour voir que ça marche.
7. Pour déconnecter : supprime le fichier `~/Library/Application Support/SaveSpace Drive/rclone.conf`. Retire aussi
   l'accès sur https://myaccount.google.com/permissions (ligne « rclone »).
8. Rapporte les chiffres des étapes 2 et 4 et ce qui t'a surpris. OneDrive et Dropbox se testent de la même façon.
