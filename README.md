# toolbox_pb

Boite a outils Python pour automatiser des traitements multimedia, principalement autour de la video et de l'image.

Le projet fournit une interface console interactive qui lit les fichiers depuis `data/input`, ecrit les resultats dans `data/output`, et s'appuie sur `FFmpeg`/`FFprobe` pour les operations de traitement.

## Fonctionnalites

Fonctionnalites actuellement disponibles dans le menu principal :

- `Video_encodor` : reencode chaque video du dossier d'entree avec les codecs configures. Les metadonnees et la taille avant/apres sont comparees.
- `Video_assemblor` : assemble plusieurs videos en un seul fichier. Si `data/segment/segments.csv` existe, il definit l'ordre des clips et leurs points de debut/fin ; sinon, les videos sont assemblees dans l'ordre des noms de fichiers.
- `Video_audio_decalator` : avance ou retarde la piste audio d'une video sans reencoder le flux video.
- `Video_volume_adjust` : applique des variations de volume audio sur des plages temporelles definies dans `data/segment/boosts.csv`, sans reencoder le flux video.
- `Video_srt_integrator` : integre `data/segment/sous_titre.srt` comme piste de sous-titres MP4 aux videos du dossier d'entree, sans reencoder l'audio ou la video.
- `Image_defilor` : genere une video verticale defilante pour chaque image source et, pour les PDF, une video par image extraite de chaque page. La hauteur, la vitesse, le FPS, les temps d'arret et le codec sont parametrables.
- `Image_diapo_video_creator` : assemble toutes les photos du dossier d'entree dans une seule video avec une duree configurable par photo. Les images sont redimensionnees sans deformation, a leur orientation EXIF reelle, et leur ratio est conserve. Une piste audio unique du dossier d'entree peut etre ajoutee ; les noms des photos et leurs timings sont integres comme piste de sous-titres dans le MP4.
- `PDF_filigranor` : ajoute a chaque PDF un filigrane textuel diagonal repete. Le menu demande le destinataire et ajoute automatiquement le prefixe configure `document exclusivement destine a`.

Entrees de menu deja prevues mais non implementees :

- `Image_reductor`
- `PDF_assemblor`
- `Flatten_directory_tree`
- `Sport_garmin_recoltor`

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
│   ├── main.py
│   ├── config_global.py
│   ├── func_global.py
│   ├── video/
│   └── image/
├── data/
│   ├── input/
│   ├── output/
│   └── segment/
├── log/
├── tests/
└── image/
```

## Flux d'utilisation

1. Deposer les fichiers sources dans `data/input`.
2. Ajouter si besoin les fichiers de parametrage dans `data/segment`.
3. Lancer la toolbox.
4. Choisir l'action dans le menu interactif.
5. Recuperer les resultats dans `data/output`.

Le projet conserve la structure des sous-dossiers de `data/input` vers `data/output` pour la plupart des traitements.

## Fichiers attendus

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

Si ce fichier n'existe pas, toutes les videos du dossier d'entree sont assemblees dans l'ordre.

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

## Diaporama video (`Image_diapo_video_creator`)

L'option `8` cree `image_diapo_video_v-<codec_video>_a-<codec_audio>.mp4` dans
`data/output`.

- Toutes les images `.jpeg`, `.jpg` et `.png` de `data/input` et de ses sous-dossiers sont prises en compte dans un ordre deterministe.
- Une image reste affichee pendant `IMAGE_DIAPO_DURATION_SECONDS` secondes (5 s par defaut).
- La sortie conserve les proportions de chaque photo et applique son orientation EXIF. Toutes les images remplissent la hauteur de trame ; de possibles bandes laterales preservent les pixels sans recadrage ni etirement.
- La hauteur est plafonnee par `IMAGE_DIAPO_MAX_HEIGHT` (2160 px par defaut) pour eviter les echecs d'encodage sur les tres grandes photos.
- Un seul fichier audio parmi `.aac`, `.flac`, `.m4a`, `.mp3`, `.ogg` et `.wav` peut etre place dans `data/input`. Il est ajoute a la video.
- Les sous-titres sont integres directement au flux MP4 : chaque entree contient le timing et le nom de la photo, sans extension. Seule la premiere annee valide a quatre chiffres du nom est conservee ; les autres chiffres sont retires.
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
- `ADD_CODEC_NAME_IN_OUTPUT` : ajoute les codecs au nom du fichier de sortie
- `PRINT_ALL_KEYS_IN_METADATA_SUMMARY` : affiche toutes les metadonnees FFprobe

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
