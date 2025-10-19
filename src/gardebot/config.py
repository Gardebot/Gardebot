"""Configuration settings for the Gardebot application."""

# GROUP_ID_GARDE_ET_PIQUET = "120363402596282813@g.us" # PROD ID POUR LE GROUPE DES GARDES
GROUP_ID_GARDE_ET_PIQUET = "120363419490068226@g.us"  # PRIVATE TEST
# GROUP_ID_GARDE_ET_PIQUET = "120363417540870860@g.us"
TIME_BEFORE_PUBLICATION_DAY = 21
PREVENTION_DAY_BEFORE_HOLIDAY = 35
MAX_NB_REMINDER = 7
# MAX_NB_REMINDER = 3
MARGIN_NOMINATION = 2  # Margin for forced nomination to ensure enough people are nominated
MINIMUM_ELAPSED_HOURS = 24  # Minimum hours before sending another reminder (set to 24 to prevent spam)

# Filenames
EVENTS_FILE = "events"
SAPEURS_FILE = "sapeurs"
VOTES_FILE = "votes"
ONDUTY_FILE = "on_duty"


MONTHS_FR = {
    1: "janvier",
    2: "février",
    3: "mars",
    4: "avril",
    5: "mai",
    6: "juin",
    7: "juillet",
    8: "août",
    9: "septembre",
    10: "octobre",
    11: "novembre",
    12: "décembre",
}

WEEKDAYS_FR = {
    0: "lundi",
    1: "mardi",
    2: "mercredi",
    3: "jeudi",
    4: "vendredi",
    5: "samedi",
    6: "dimanche",
}

EM_NAME = [
    # "Vadim Harych",
    # "David Gori",
    # "Julien Haefelin",
    # "Louis Bretton",
    # "Jean-Seb Fourier",
    # "Damien Neuenschwander",
    # "Liberto Christophe",
    # "Vincent Vuillemier",
    # "Eilean Rieder",
    # "Lionel Bidaux",
    # "Christophe Zurn",
    "eSim Swisscom",
]
