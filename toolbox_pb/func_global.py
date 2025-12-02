"""
Ce fichier contient des fonctions communes utilitaires pour la toolbox_pb

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Imports standard
from functools import wraps
import time


def transform_sec_duration_in_min_sec(start, end):
    """
    This function calculates the duration between two time points in 
    minutes and seconds.
    """
    min, sec = divmod(end - start, 60)
    return int(min), int(sec)

def measure_time(func):
    """
    Décorateur pour mesurer le temps d'exécution d'une fonction.
    """
    @wraps((func))
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration_sec = time.perf_counter() - start
        min, sec = transform_sec_duration_in_min_sec(0, duration_sec)
        print(
            f"⏱️ Temps d'exécution de {func.__name__} : "
            f"{min} min et {sec} sec.")
        return result
    return wrapper

def print_step(step_num, message):
    """
    Print a formatted step message for process reporting.
    """
    print("\n\n" + "*" * 100)
    print(f"==> STEP {step_num} : {message} <==")
    print("*" * 100 + "\n")

def exit_toolbox():
    print("\nAu revoir !")
    exit()
