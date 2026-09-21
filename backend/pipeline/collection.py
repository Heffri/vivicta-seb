"""Curated Wallenberg and data-derived SEB Mid Cap collections.
Sources: https://www.investorab.com/our-companies/ and https://fam.se/
A holdings collection, not a claim of majority ownership or an exhaustive family tree.
Kept with application code so existing installations receive roster updates.
"""
import json
import re
import unicodedata

from . import paths

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

def _midcap_members():
    companies = json.loads(paths.companies_path().read_text(encoding='utf-8'))
    return frozenset(identity(company['name']) for company in companies if company.get('market') == 'Mid Cap')


# Read the source once at application startup. Do not duplicate this roster in code: the data
# directory is the authoritative SEB universe, while identity() handles catalog spelling variants.
MIDCAP = _midcap_members()


def members(collection_name):
    if collection_name == 'wallenberg':
        return frozenset(NAMES)
    if collection_name == 'midcap':
        return MIDCAP
    if collection_name == 'all':
        return None
    raise ValueError(f'unknown collection: {collection_name}')


def scope(collection_name):
    names = members(collection_name)
    return lambda name: names is None or identity(name) in names


def member(name, collection_name='wallenberg'):
    # Preserve the Wallenberg group metadata used by existing callers and tests.
    if collection_name == 'wallenberg':
        return NAMES.get(identity(name))
    return scope(collection_name)(name)


def directory(companies, collection_name='wallenberg'):
    if collection_name == 'all':
        return companies
    if collection_name == 'midcap':
        in_scope = scope(collection_name)
        return [company for company in companies if in_scope(company['name'])]
    existing = {identity(c['name']): c for c in companies}
    return [dict(existing.get(key, {'ticker': '', 'sector': None, 'isin': None}), name=name, collection_group=group)
            for key, (name, group) in NAMES.items()]
