"""Company-name identity, plus the curated Wallenberg roster the company directory merges in.
Sources: https://www.investorab.com/our-companies/ and https://fam.se/
A holdings roster, not a claim of majority ownership or an exhaustive family tree.
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

# Parent-report context does not establish whether a subsidiary publishes its own accounts.
# Preserve this mapping for the company map, but allow standalone discovery for every issuer.
NO_STANDALONE_REPORTS = {
    'Atlas Antibodies': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'BraunAbility': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Laborie': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Mölnlycke': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Nova Biomedical': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Permobil': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Piab': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Sarnova': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    '3 Scandinavia': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Vectura': {'reports_in': 'Investor AB', 'collection_group': 'Patricia Industries', 'report_stem': 'investor_2025'},
    'Kopparfors Skogar': {'reports_in': 'FAM AB', 'collection_group': 'FAM holdings', 'report_stem': None},
    'The Grand Group': {'reports_in': 'FAM AB', 'collection_group': 'FAM holdings', 'report_stem': None},
    'Kivra': {'reports_in': 'FAM AB', 'collection_group': 'FAM holdings', 'report_stem': None},
}

def normalize(name):
    text = ''.join(c for c in unicodedata.normalize('NFKD', name or '') if not unicodedata.combining(c)).casefold()
    words = re.sub(r'[^a-z0-9]+', ' ', text).split()
    return ' '.join(w for w in words if w not in {'ab', 'oyj', 'plc', 'ltd', 'inc', 'group', 'publ', 'svenska'})

NAMES = {normalize(name): (name, group) for group, names in GROUPS.items() for name in names}
NO_STANDALONE = {normalize(name): metadata for name, metadata in NO_STANDALONE_REPORTS.items()}
ALIASES = {'swedish orphan biovitrum': 'sobi', 'skandinaviska enskilda banken': 'seb', 'molnlycke health care': 'molnlycke', 'grand': 'the grand',
           'vectura fastigheter': 'vectura', 'hi3g scandinavia': '3 scandinavia'}

def identity(name):
    key = normalize(name)
    return ALIASES.get(key, key)

def member(name):
    """The roster entry for a company, as (display name, group), or None. Prompt context only."""
    return NAMES.get(identity(name))


def report_metadata(name):
    """Parent-report context, without assuming standalone accounts are unavailable."""
    metadata = NO_STANDALONE.get(identity(name))
    return dict(metadata) | {'no_standalone_report': False} if metadata else None


def reported_members(report_owner):
    """Private roster names disclosed in a saved parent report (for KB/map context)."""
    return [dict(name=name, collection_group=metadata['collection_group'])
            for name, metadata in NO_STANDALONE_REPORTS.items() if metadata['reports_in'] == report_owner]


def directory(companies):
    """The whole catalogue, plus the roster names it does not list. Those extra rows are the only
    way private holdings such as Moelnlycke are findable at all -- they have no catalogue entry --
    so they are merged in rather than filtered for, and nothing is ever hidden."""
    existing = {identity(c['name']) for c in companies}
    extra = []
    for key, (name, group) in NAMES.items():
        if key in existing:
            continue
        row = {'ticker': '', 'sector': None, 'isin': None, 'name': name, 'collection_group': group}
        if metadata := report_metadata(name):
            row.update(metadata)
        extra.append(row)
    return companies + extra
