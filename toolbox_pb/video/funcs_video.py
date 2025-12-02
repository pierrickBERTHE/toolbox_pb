"""
Ce fichier contient des fonctions pour les actions sur les vidéos

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Imports standard
from moviepy import VideoFileClip

# Import custom librairies
from func_global import measure_time

@measure_time
def encode_full_video(input_path, output_path, codec_video, codec_audio):
    clip = VideoFileClip(str(input_path))
    clip.write_videofile(
        str(output_path),
        codec= codec_video,
        audio_codec = codec_audio,
        threads=4,
        logger="bar"
    )
    clip.close()
