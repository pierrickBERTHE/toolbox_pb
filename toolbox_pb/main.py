"""
Ce fichier contient le script principal de la toolbox_pb

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Import custom librairies
from video.main_video import video_encodor
from func_global import exit_toolbox

# Main code
if __name__ == "__main__":
    print("\nMenu principal : ")
    print("1. Vidéo assemblor")
    print("2. Vidéo splitter")
    print("3. Quitter")
    # choix = input("Sélectionnez une option (1-3) : ")
    choix = "1"

    # Match the case by the input
    match choix:
        case "1":
            print("\nLancement du video_encodor...")
            video_encodor()
        case "2":
            print("\nLancement du video_splitter...")
            # A FAIRE
        case "3":
            exit_toolbox()
        case _:
            print("Choix invalide, recommencez.")

    
    
    # pouvoir choisir le fichier avec input ou on veut sur le PC
