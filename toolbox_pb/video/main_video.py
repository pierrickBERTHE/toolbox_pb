from pathlib import Path
import video.funcs_video as func_vid
import func_global as func_glob
import config_global as config


def video_encodor():
    """
    description
    """
    
    # Video and audio codecs
    accepted_file = config.INPUT_ACCEPTED_FILES
    codec_v = config.CODEC_VIDEO
    codec_a = config.CODEC_AUDIO
    suffix = config.SUFFIX_OUTPUT

    # input and oupt paths
    input_dir = config.INPUT_DIR
    output_dir = config.OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)

    # Iterate on each file in input_dir
    for input_file in input_dir.iterdir():
        
        # Create de output file and path
        output_name = (f"{input_file.stem}_v-{codec_v}_a-{codec_a}{suffix}")
        output_path = output_dir / output_name
        
        # Define flag
        output_file_exist = False
        
        # Ignore the file type
        if input_file.suffix.lower() not in accepted_file:
            continue
        
        # Ignore the output_file already exist
        if output_path in output_dir.iterdir():
            output_file_exist = True
        
        # STEP 1 : encode the video if needed
        func_glob.print_step(1, f"Encodage de la vidéo : {input_file.name}")
        if output_file_exist:
            print("Encodage déjà réalisé")
            pass
        else:
            func_vid.encode_full_video(
                input_path=input_file,
                output_path=output_path,
                codec_video = codec_v,
                codec_audio = codec_a
            )

