# toolbox_pb

Boite a outils Python pour automatiser des traitements multimedia, principalement autour de la video et de l'image.

Le projet fournit une interface console interactive qui lit les fichiers depuis `data/input`, ecrit les resultats dans `data/output`, et s'appuie sur `FFmpeg`/`FFprobe` pour les operations de traitement.

## Fonctionnalites

Fonctionnalites actuellement disponibles dans le menu principal :
`-- VIDEO --`
- `Video_encodor` : reencode chaque video du dossier d'entree avec les codecs configures. Une barre de progression, les comparaisons de taille et un bilan global sont affiches. Il ne copie pas les images : elles sont reservees a `Image_reductor`. Le MP4 de sortie contient un commentaire de suivi de traitement.
- `Video_assemblor` : assemble plusieurs videos en un seul fichier. Si `data/segment/segments.csv` existe, il definit l'ordre des clips et leurs points de debut/fin ; sinon, les videos sont assemblees dans l'ordre des noms de fichiers. Chaque clip est redimensionne sans deformation pour remplir toute la hauteur de la trame commune ; les formats portrait et paysage peuvent donc etre assembles sans bandes en haut ou en bas. Les sous-titres deja integres aux sources sont conserves et leurs timings sont recalcules ; une piste de dates est ajoutee si le flag correspondant est active. Le MP4 assemble contient un commentaire de suivi de traitement.
- `Video_audio_decalator` : avance ou retarde la piste audio d'une video sans reencoder le flux video.
- `Video_volume_adjust` : applique des variations de volume audio sur des plages temporelles definies dans `data/segment/boosts.csv`, sans reencoder le flux video.
- `Video_srt_extractor` : extrait la piste de sous-titres deja integree a chaque video du dossier d'entree vers un fichier `.srt` independant place a cote de la video, et produit une copie de la video sans cette piste, sans reencoder l'audio ou la video. Les videos sans piste de sous-titres sont ignorees : rien n'est ecrit dans `data/output` pour elles.
- `Video_srt_integrator` : integre `data/segment/sous_titre.srt` comme piste de sous-titres MP4 aux videos du dossier d'entree, sans reencoder l'audio ou la video.
`-- IMAGE --`
- `Image_defilor` : genere une video verticale defilante pour chaque image source et, pour les PDF, une video par image extraite de chaque page. La hauteur, la vitesse, le FPS, les temps d'arret et le codec sont parametrables.
- `Image_reductor` : reduit les photos JPEG/PNG sans changer leur format ni leurs dimensions. Une barre de progression, la comparaison de poids globale et un bilan des images compressees, intactes et deja traitees sont affiches. Les JPEG sont reencodes en qualite 95, les PNG sont optimises sans perte ; orientation EXIF, profil colorimetrique et transparence sont conserves. Les images non allegeables et les documents non-video sont copies intacts ; les videos compatibles sont reservees a `Video_encodor`. Les copies JPEG incluent un commentaire de suivi de traitement.
- `Image_diapo_video_creator` : assemble toutes les photos du dossier d'entree dans une seule video avec une duree configurable par photo. Les images sont redimensionnees sans deformation, a leur orientation EXIF reelle, et leur ratio est conserve. Une piste audio unique du dossier d'entree peut etre ajoutee ; les noms des photos et leurs timings sont integres comme piste de sous-titres dans le MP4.
`-- PDF --`
- `PDF_filigranor` : ajoute a chaque PDF un filigrane textuel diagonal repete. Le menu demande le destinataire et ajoute automatiquement le prefixe configure `document exclusivement destine a`.
- `PDF_assemblor` : fusionne tous les PDF du dossier d'entree (et de ses sous-dossiers) dans un unique fichier, dans l'ordre alphabetique de leurs chemins relatifs.
`-- FILE --`
- `File_timeline_sorter` : copie les fichiers du dossier d'entree vers le dossier de sortie avec leur date de derniere modification (`AAAA-MM-JJ_HH-MM-SS__nom-original.ext`) afin que le tri alphabetique corresponde a l'ordre chronologique. Les fichiers source restent intacts.

## Prerequis

- Python `>= 3.12`
- [Poetry](https://python-poetry.org/)
- [FFmpeg](https://ffmpeg.org/download.html) installe et accessible dans le `PATH`

Sans `FFmpeg` et `FFprobe`, les traitements video/image ne fonctionneront pas.

## Installation

```bash
poetry install
```

Pour verifier l'environnement :

```bash
poetry run pytest
```

## Lancement

Depuis la racine du projet :

```bash
poetry run python toolbox_pb/main.py
```

Sous Windows, un lanceur est aussi present :

```bat
execute_toolbox.bat
```

## Deploiement avec Docker (Windows 11)

Cette methode inclut Python, FFmpeg et FFprobe dans le conteneur : aucune
installation de Python, Poetry ou FFmpeg n'est necessaire sur le PC cible.

1. Installer [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   sur le PC Windows 11 cible et verifier qu'il utilise les conteneurs Linux.
2. Copier tout le dossier du projet sur ce PC (ou le cloner depuis son depot Git).
3. Ouvrir PowerShell dans le dossier du projet et lancer :

   ```powershell
   docker compose run --rm --build toolbox
   ```

   Au premier lancement, Docker construit l'image et telecharge les dependances.
   Les lancements suivants reutilisent l'image. Le fichier
   `run_toolbox_docker.bat` permet d'executer la meme commande par double-clic.

Les dossiers locaux `data/input`, `data/output`, `data/segment` et `log` sont
montes dans le conteneur. Deposez donc les fichiers sources dans `data/input`
sur Windows, utilisez le menu dans la console, puis recuperer les fichiers
generes dans `data/output` sur Windows.

Pour reconstruire l'image apres une mise a jour du code :

```powershell
docker compose build --no-cache
```

### Transfert de l'image par Internet (Docker Hub)

Sur le PC de construction, apres avoir cree un compte Docker Hub, remplacez
`MON_COMPTE` par votre identifiant Docker Hub puis publiez l'image :

```powershell
docker login
docker compose build
docker tag toolbox-pb:1.0.0 MON_COMPTE/toolbox-pb:1.0.0
docker push MON_COMPTE/toolbox-pb:1.0.0
```

Sur le PC cible, dans PowerShell, telechargez et utilisez l'image publiee :

```powershell
docker login  # seulement si le depot Docker Hub est prive
$env:TOOLBOX_IMAGE = "MON_COMPTE/toolbox-pb:1.0.0"
docker compose pull
docker compose run --rm toolbox
```

Le nom de l'image peut etre rendu permanent sur le PC cible en creant un
fichier `.env` a la racine du projet contenant :

```text
TOOLBOX_IMAGE=MON_COMPTE/toolbox-pb:1.0.0
```

## Organisation du projet

```text
toolbox_pb/
├── toolbox_pb/
│   ├── main.py                 # menu et routage des options 1 a 14
│   ├── config_global.py        # chemins, extensions, codecs et flags
│   ├── func_global.py          # fonctions communes a toute l'application
│   ├── reductor_workflow.py    # enchainement Video_encodor / Image_reductor
│   ├── video/
│   │   ├── main_video.py       # options 1 a 6 et 9
│   │   └── func_video.py       # traitements FFmpeg, MoviePy et SRT
│   ├── image/
│   │   ├── main_image.py       # options 7, 8 et 10
│   │   └── func_image.py       # traitements et metadonnees image
│   ├── pdf/
│   │   ├── main_pdf.py         # options 11 et 12
│   │   └── func_pdf.py         # filigrane et fusion PDF
│   └── file/
│       ├── main_file.py        # option 13
│       └── func_file.py        # datation et copie des fichiers
├── data/
│   ├── input/                  # fichiers sources a traiter
│   ├── output/                 # fichiers generes (jamais relus comme entree)
│   └── segment/                # fichiers de parametrage CSV et SRT
├── docs/                       # documents et diagrammes explicatifs
├── image/                      # icones et captures du projet
├── log/                        # journal process_log.txt si LOG_TO_FILE=True
├── tests/                      # tests unitaires pytest
├── Dockerfile / compose.yaml   # execution dans Docker
├── pyproject.toml              # dependances et configuration Poetry/pytest
└── README.md
```

## Flux d'utilisation

1. Deposer les fichiers sources dans `data/input`.
2. Ajouter si besoin les fichiers de parametrage dans `data/segment`.
3. Lancer la toolbox.
4. Choisir l'action dans le menu interactif.
5. Recuperer les resultats dans `data/output`.

Le projet conserve la structure des sous-dossiers de `data/input` vers `data/output` pour la plupart des traitements.

## Fichiers attendus

### Regles communes

- Deposez uniquement les sources dans `data/input` ; `data/output` est reserve
  aux resultats et n'est jamais traite comme une entree.
- Les sous-dossiers de `data/input` sont acceptes. Ils sont conserves dans
  `data/output` lorsque la fonctionnalite produit un fichier par source.
- Le fichier `.gitkeep`, les dossiers et les fichiers deja presents dans
  `data/output` sont exclus de tous les traitements.
- Extensions video acceptees : `.avi`, `.m4v`, `.mkv`, `.mod`, `.mov`, `.mp4`,
  `.mpg`, `.mts`, `.vob`, `.webm`.
- Extensions image acceptees : `.jpeg`, `.jpg`, `.png`. Extensions PDF :
  `.pdf`. Extensions audio du diaporama : `.aac`, `.flac`, `.m4a`, `.mp3`,
  `.ogg`, `.wav`.

### Par fonctionnalite

| Option | Fonctionnalite | Fichiers places dans `data/input` | Fichier supplementaire dans `data/segment` | Resultat dans `data/output` |
| --- | --- | --- | --- | --- |
| 1 | `Video_encodor` | Une ou plusieurs videos acceptees | Aucun | Une video reencodee par source, avec la structure des sous-dossiers conservee |
| 2 | `Video_assemblor` | Une ou plusieurs videos acceptees | `segments.csv` facultatif | Un seul MP4 `assembled_v-<codec>_a-<codec>.mp4` |
| 3 | `Video_audio_decalator` | Une ou plusieurs videos acceptees | Aucun : le decalage, positif ou negatif, est demande dans le terminal | Une video decalee par source |
| 4 | `Video_volume_adjust` | Une ou plusieurs videos acceptees | `boosts.csv` requis | Une video ajustee par source |
| 5 | `Video_srt_extractor` | Une ou plusieurs videos acceptees | Aucun | Pour chaque video contenant une piste de sous-titres : un fichier `.srt` et une copie de la video sans cette piste. Les videos sans sous-titres sont ignorees : rien n'est ecrit |
| 6 | `Video_srt_integrator` | Une ou plusieurs videos acceptees | `sous_titre.srt` requis | Une video avec piste de sous-titres par source |
| 7 | `Image_defilor` | Images acceptees et/ou PDF | Aucun | Une video defilante par image ou page PDF |
| 8 | `Image_reductor` | Images, et eventuellement autres fichiers a copier | Aucun | Images reduites et copies intactes des fichiers non-video |
| 9 | `Image_diapo_video_creator` | Images acceptees ; un audio facultatif | Aucun | Un MP4 de diaporama avec piste de sous-titres |
| 10 | `Image_withoutbg` | Images acceptees | Aucun | Une image sans arriere-plan par source |
| 11 | `PDF_filigranor` | Un ou plusieurs PDF | Aucun ; le destinataire est demande au menu | Un PDF filigrane par source |
| 12 | `PDF_assemblor` | Un ou plusieurs PDF | Aucun | Un seul PDF `pdf_assemblage.pdf` |
| 13 | `File_timeline_sorter` | Tout fichier source sauf `.gitkeep` | Aucun | Une copie par fichier, prefixee par sa date de modification |

`Video_assemblor` et `PDF_assemblor` classent leurs entrees par chemin relatif
dans `data/input` lorsqu'aucun ordre explicite n'est fourni. Pour les autres
fonctionnalites, l'ordre n'a d'importance que lorsqu'il est indique ci-dessous.

### `data/segment/segments.csv`

Utilise par `Video_assemblor`.

Colonnes attendues :

- `filename`
- `start`
- `end`

Exemple :

```csv
filename,start,end
clip_01.mp4,00:00:05,00:00:15
clip_02.mp4,00:00:00,00:00:08
clip_01.mp4,00:00:20,00:00:30
```

Ce fichier est facultatif. Chaque ligne choisit une video, son ordre et la
plage a conserver. Un meme fichier peut etre present plusieurs fois. Les temps
acceptent `HH:MM:SS`, `MM:SS` ou un nombre de secondes.

Si ce fichier n'existe pas, toutes les videos de `data/input` et de ses
sous-dossiers sont assemblees par ordre alphabetique de leur chemin relatif.
Les sous-titres deja contenus dans les videos sont conserves et leurs timings
sont recalcules dans la nouvelle video.

### `data/segment/boosts.csv`

Utilise par `Video_volume_adjust`.

Colonnes attendues :

- `start`
- `end`
- `gain_db`

Exemple :

```csv
start,end,gain_db
00:00:10,00:00:20,4
00:01:05,00:01:12,-3
```

La valeur `gain_db` est volontairement limitee a `+/- 20 dB`.

Chaque ligne applique le gain indique entre `start` et `end`. Les temps
acceptent le meme format que `segments.csv`.

### `data/segment/sous_titre.srt`

Utilise par `Video_srt_integrator`.

Exemple :

```srt
1
00:00:01,000 --> 00:00:03,000
Bonjour

2
00:00:04,000 --> 00:00:06,000
Sous-titre de demonstration
```

Le meme fichier SRT est integre a chaque video source traitee par l'option 6.

### Aucun fichier de parametrage requis

- `Video_encodor`, `Video_audio_decalator`, `Video_srt_extractor`,
  `Image_reductor`, `Image_withoutbg`, `PDF_filigranor`, `PDF_assemblor` et
  `File_timeline_sorter` ne demandent aucun fichier dans `data/segment`.
  `Video_srt_extractor` lit directement la piste de sous-titres deja
  presente dans chaque video source : aucun fichier externe n'est necessaire.
- `Image_defilor` se configure au lancement par les options affichees dans le
  menu ; voir la section suivante pour les parametres disponibles.
- `Image_diapo_video_creator` accepte un seul fichier audio facultatif dans
  `data/input`, en plus des images. S'il y a plusieurs fichiers audio, il faut
  n'en laisser qu'un pour obtenir un resultat non ambigu.

## Diaporama video (`Image_diapo_video_creator`)

L'option `9` cree `image_diapo_video_v-<codec_video>_a-<codec_audio>.mp4` dans
`data/output`.

- Toutes les images `.jpeg`, `.jpg` et `.png` de `data/input` et de ses sous-dossiers sont prises en compte dans un ordre deterministe.
- Une image reste affichee pendant `IMAGE_DIAPO_DURATION_SECONDS` secondes (5 s par defaut).
- La sortie conserve les proportions de chaque photo et applique son orientation EXIF. Toutes les images remplissent la hauteur de trame ; de possibles bandes laterales preservent les pixels sans recadrage ni etirement.
- La hauteur est plafonnee par `IMAGE_DIAPO_MAX_HEIGHT` (2160 px par defaut) pour eviter les echecs d'encodage sur les tres grandes photos.
- Un seul fichier audio parmi `.aac`, `.flac`, `.m4a`, `.mp3`, `.ogg` et `.wav` peut etre place dans `data/input`. Il est ajoute a la video.
- Les sous-titres sont integres directement au flux MP4 : chaque entree contient le timing et le nom de la photo, sans extension. Pour une date numerique complete ou annee-mois, seule la premiere annee valide a quatre chiffres est conservee ; les autres chiffres du nom (par exemple un age) sont conserves.
- L'encodage est realise photo par photo puis assemble, afin de limiter la consommation de memoire. Deux barres `tqdm` indiquent la photo en cours et la progression globale.

## Parametres d'`Image_defilor`

Lors du lancement de l'option image, des arguments supplementaires peuvent etre saisis.

Options disponibles :

- `--height` : hauteur de sortie, par defaut `1080`
- `--speed` : vitesse de defilement en px/s, par defaut `35`
- `--fps` : images par seconde, par defaut `60`
- `--hold-start` : duree d'attente au debut, par defaut `5`
- `--hold-end` : duree d'attente a la fin, par defaut `5`
- `--codec` : codec video de sortie, par defaut `libx265`
- `--crf` : niveau de compression, par defaut `18`

Exemple de saisie :

```text
--height 720 --speed 50 --fps 30 --hold-start 2 --hold-end 2 --codec libx264 --crf 20
```

## Extraction et integration de sous-titres

`Video_srt_extractor` (option `5`) et `Video_srt_integrator` (option `6`) sont
symetriques et n'effectuent aucun reencodage audio/video (`-c copy`) : seul le
flux de sous-titres est ajoute, retire ou converti.

- `Video_srt_extractor` analyse chaque video avec `FFprobe`. Si aucune piste de
  sous-titres n'est detectee, la video est entierement ignoree : aucun fichier
  n'est ecrit dans `data/output` pour elle. Si une piste est detectee, la
  premiere piste de sous-titres est extraite vers `<nom>.srt`, et une copie de
  la video sans cette piste est ecrite a cote sous le meme nom.
- `Video_srt_integrator` fait l'inverse : il ajoute `sous_titre.srt` comme
  piste `mov_text` a chaque video du dossier d'entree.

Ces deux options ne modifient jamais les fichiers de `data/input`.

## Reducteurs image et video

Les options `Video_encodor` et `Image_reductor` traitent les fichiers de
maniere recursive et conservent les sous-dossiers de `data/input` dans
`data/output`.

- `Image_reductor` traite les `.jpeg`, `.jpg` et `.png`. Les JPEG sont
  reencodes a la qualite 95 sans redimensionnement ; les PNG sont optimises
  sans perte. Une image qui ne deviendrait pas plus legere est copiee telle
  quelle. Les documents non-video (par exemple PDF et DOCX) sont aussi copies
  intacts. Les formats video acceptes ne sont pas copies afin d'eviter les
  doublons avec `Video_encodor`.
- `Video_encodor` traite uniquement les formats video acceptes et ne copie pas
  les images. Le filtre de mise a l'echelle force des dimensions paires lorsque
  necessaire, pour rester compatible avec `libx265`.
- Les deux traitements disposent d'une barre `tqdm` globale et d'un bilan en
  fin de traitement. `Image_reductor` affiche en plus une comparaison de taille
  cumulee des fichiers effectivement compresses.
- Si le dossier d'entree contient aussi des fichiers de l'autre type, la
  toolbox propose de lancer le reducteur complementaire. La reponse par defaut
  est oui apres un compte a rebours de 10 secondes ; entrer `n` ou `non` avant
  l'echeance annule ce second traitement. Le reducteur declenche ne demande pas
  a relancer le premier : aucune boucle ne peut se produire.

### Commentaires de suivi dans les metadonnees

Seules les fonctionnalites `Video_encodor`, `Video_assemblor` et
`Image_reductor` inscrivent un commentaire de suivi dans le fichier genere.
`Video_srt_extractor` et `Video_srt_integrator` ne font que remuxer le flux de
sous-titres (`-c copy`) et n'ajoutent pas de nouvelle ligne d'historique ; un
commentaire deja present sur la video source est cependant conserve tel quel,
puisque FFmpeg reporte les metadonnees globales du fichier d'entree par
defaut lors d'un remux. Les fichiers places dans `data/input` ne sont jamais
modifies.

Le commentaire construit un historique multi-lignes, une ligne par
traitement subi par le fichier :

```text
toolbox_pb | 
traitement n°1 : video_assemblor | Vidéo : libx265 | Audio : aac
traitement n°2 : video_encodor | Vidéo : libx265 | Audio : aac
```

- Une nouvelle ligne `traitement n°N : ...` est ajoutee lorsqu'un fichier deja
  porteur de ce commentaire est utilise comme source par `Video_encodor` ou
  `Image_reductor` ; `N` reprend le dernier numero trouve dans l'historique,
  incremente de un.
- `Video_assemblor` lit l'historique du fichier source pour la comparaison de
  metadonnees mais initialise toujours le sien a `traitement n°1`, puisque le
  fichier assemble regroupe plusieurs sources distinctes.
- Pour les MP4, le commentaire est ajoute pendant la creation initiale du
  fichier par FFmpeg/MoviePy afin d'etre lisible dans la propriete
  **Commentaires** de l'Explorateur Windows.
- Pour les JPEG, la valeur est ecrite dans la metadonnee EXIF `XPComment`,
  utilisee par la propriete **Commentaires** de l'Explorateur Windows. Les PNG
  contiennent aussi un champ `Comment`, dont l'affichage depend du lecteur.
- Les autres fonctionnalites ne modifient pas cet historique.

### Noms de sortie

Les fichiers reels compresses peuvent etre identifies sans renommer les copies
intactes :

- `ADD_CODEC_NAME_IN_OUTPUT=True` ajoute uniquement le codec vidéo avant
  l'extension des vidéos réencodées, par exemple `clip_libx265.mp4`.
- `ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT=True` ajoute `_compress_<qualité>`
  avant l'extension des JPEG effectivement réduits, par exemple
  `photo_compress_95.jpg`. Les PNG gardent le suffixe `_compress` car ils ne
  reçoivent pas de qualité JPEG.
- `IMAGE_REDUCTOR_JPEG_QUALITY` définit la qualité JPEG du réducteur ; sa
  valeur par défaut est `95`.

Ce réglage est regroupé avec les autres flags utilisateur en tête de
`toolbox_pb/config_global.py`.

## Configuration

La configuration globale est centralisee dans [toolbox_pb/config_global.py](/c:/Users/pierr/VSC_Projects/toolbox_pb/toolbox_pb/config_global.py).

Points importants :

- dossiers racine : `log`, `data/input`, `data/output`, `data/segment`
- codecs video supportes : `libx264`, `libx265`, `h264_amf`, `hevc_amf`
- codec audio par defaut : `aac`
- extensions video : `.avi`, `.m4v`, `.mkv`, `.mod`, `.mov`, `.mp4`, `.mpg`, `.mts`, `.vob`, `.webm`
- extensions image : `.jpeg`, `.jpg`, `.png`
- extensions audio pour le diaporama : `.aac`, `.flac`, `.m4a`, `.mp3`, `.ogg`, `.wav`
- extensions pdf : `.pdf`

Parametres du diaporama :

- `IMAGE_DIAPO_DURATION_SECONDS` : duree d'affichage de chaque image, par defaut `5.0`
- `IMAGE_DIAPO_FPS` : cadence de sortie, par defaut `24`
- `IMAGE_DIAPO_MAX_HEIGHT` : hauteur maximale de la sortie, par defaut `2160`

Flags disponibles :

- `LOG_TO_FILE` : redirige les sorties console vers `log/process_log.txt`
- `ADD_CODEC_NAME_IN_OUTPUT` : ajoute le codec vidéo au nom des vidéos
  réencodées
- `ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT` : ajoute `_compress_<qualité>` aux
  JPEG réellement réduits et `_compress` aux PNG
- `IMAGE_REDUCTOR_JPEG_QUALITY` : règle la qualité JPEG du réducteur, de `0`
  à `100`
- `PRINT_ALL_KEYS_IN_METADATA_SUMMARY` : affiche toutes les metadonnees FFprobe
- `VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES` : ajoute une piste SRT de date au fichier
  assemble. Chaque date trouvee dans le nom d'une video source est affichee au
  debut de son clip pendant cinq secondes, au format `JJ/MM/AAAA`. Les pistes
  de sous-titres deja presentes dans les videos sources sont aussi conservees,
  recadrees si un segment est selectionne, puis decalees sur la nouvelle
  chronologie de l'assemblage.

## Tests

La suite de tests couvre notamment :

- le routage du menu principal
- la configuration globale
- les utilitaires communs
- les traitements image
- les traitements video

Execution :

```bash
poetry run pytest
```

## Notes

- Le projet est oriente usage local et interactif.
- Les operations reposent fortement sur `FFmpeg`, donc les performances et la compatibilite dependent de l'installation locale.
- L'encodage video peut exploiter plusieurs threads CPU.
