"""Curated Wallenberg collection, verified 2026-09-18.
Sources: https://www.investorab.com/our-companies/ and https://fam.se/
A holdings collection, not a claim of majority ownership or an exhaustive family tree.
Kept with application code so existing installations receive roster updates.
"""
import re
import unicodedata

GROUPS = {
    'Holding companies': ['Investor AB', 'FAM AB'],
    'Investor listed holdings': ['ABB', 'AstraZeneca', 'Atlas Copco', 'Electrolux', 'Electrolux Professional', 'Epiroc', 'Ericsson', 'Husqvarna', 'Nasdaq', 'Saab', 'SEB', 'Sobi', 'Wärtsilä'],
    'Investor investment in EQT': ['EQT'],
    'Patricia Industries': ['Atlas Antibodies', 'BraunAbility', 'Laborie', 'Mölnlycke', 'Nova Biomedical', 'Permobil', 'Piab', 'Sarnova', '3 Scandinavia', 'Vectura'],
    'FAM holdings': ['SKF', 'Stora Enso', 'Munters', 'IPCO', 'Kopparfors Skogar', 'The Grand Group', 'Höganäs', 'Nefab', 'Kivra'],
}

def normalize(name):
    text = ''.join(c for c in unicodedata.normalize('NFKD', name or '') if not unicodedata.combining(c)).casefold()
    words = re.sub(r'[^a-z0-9]+', ' ', text).split()
    return ' '.join(w for w in words if w not in {'ab', 'oyj', 'plc', 'ltd', 'inc', 'group', 'publ', 'svenska'})

NAMES = {normalize(name): (name, group) for group, names in GROUPS.items() for name in names}
ALIASES = {'swedish orphan biovitrum': 'sobi', 'skandinaviska enskilda banken': 'seb', 'molnlycke health care': 'molnlycke', 'grand': 'the grand'}

def identity(name):
    key = normalize(name)
    return ALIASES.get(key, key)

def member(name):
    return NAMES.get(identity(name))

def directory(companies):
    existing = {identity(c['name']): c for c in companies}
    return [dict(existing.get(key, {'ticker': '', 'sector': None, 'isin': None}), name=name, collection_group=group)
            for key, (name, group) in NAMES.items()]
