"""Main workflows for file-management features."""

from config_global import AppConfig
import toolbox_pb.file.func_file as func_file
import func_global as func_glob


@func_glob.measure_time
def file_timeline_sorter(cfg: AppConfig) -> bool:
    """Copy input files with modification-date prefixes for chronological sorting."""

    # Get all processable files in the input directory and its subdirectories
    input_files = sorted(
        (
            path
            for path in cfg.INPUT_DIR.rglob("*")
            if func_glob.is_processable_file(path)
        ),
        key=lambda path: str(path.relative_to(cfg.INPUT_DIR)).casefold(),
    )

    # If no files were found, return True
    if not input_files:
        return True

    # Process each file and copy it to the output directory with a timeline prefix
    copied_files = 0
    for input_path in input_files:
        relative_path = input_path.relative_to(cfg.INPUT_DIR)
        output_subdir = cfg.OUTPUT_DIR / relative_path.parent
        filename = input_path.name
        if not func_file.is_timeline_filename(filename):
            modification_time = func_file.get_file_modification_time(input_path)
            filename = func_file.build_timeline_filename(input_path, modification_time)
        output_path = output_subdir / filename

        if func_file.copy_file_for_timeline(input_path, output_path):
            print(f"Fichier redaté : {input_path.name} -> {output_path.name}")
            copied_files += 1
        else:
            print(f"Redatage déjà réalisé : {input_path.name}")

    print(f"{copied_files} fichier(s) redaté(s).")
    return False
