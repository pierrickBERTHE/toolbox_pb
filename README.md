# toolbox_pb

Boite a outils Python pour automatiser des traitements multimedia, principalement autour de la video et de l'image.

Le projet fournit une interface console interactive qui lit les fichiers depuis `data/input`, ecrit les resultats dans `data/output`, et s'appuie sur `FFmpeg`/`FFprobe` pour les operations de traitement.

## Fonctionnalites

Fonctionnalites actuellement disponibles dans le menu principal :

- `Video_encodor` : reencode les videos du dossier d'entree avec les codecs configures, compare les metadonnees avant/apres et affiche le gain de taille.
- `Video_assemblor` : assemble plusieurs videos en un seul fichier. Si `data/segment/segments.csv` existe, l'ordre et les coupes sont pris depuis ce fichier.
- `Video_audio_decalator` : decale la piste audio d'une video sans reencoder le flux video.
- `Video_volume_adjust` : applique des boosts audio sur des plages temporelles definies dans `data/segment/boosts.csv`.
- `Video_srt_integrator` : ajoute un fichier `sous_titre.srt` aux videos du dossier d'entree.
- `Image_defilor` : genere une video verticale defilante a partir d'une image, avec hauteur, vitesse, FPS et codec parametrables.

Entrees de menu deja prevues mais non implementees :

- `Image_reductor`
- `PDF_filigranor`
- `PDF_assemblor`
- `Flatten_directory_tree`

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
- extensions image : `.jpg`, `.png`
- extensions pdf : `.pdf`

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
