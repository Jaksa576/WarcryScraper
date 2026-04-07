#!/usr/bin/env python3
"""Export Scrapy crawl output to multiple Markdown files organized by type and faction."""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List
from collections import defaultdict

import sys
sys.path.insert(0, str(Path(__file__).parent))
from search import build_documents


def slugify(text: str) -> str:
    """Convert text to a safe filename slug.
    
    Converts to lowercase, replaces spaces and special characters (colons, hyphens, apostrophes)
    with underscores, and strips any double underscores.
    
    Example: "Cities of Sigmar: Castelite Hosts" → "cities_of_sigmar_castelite_hosts"
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace colons, hyphens, and apostrophes with underscores
    slug = re.sub(r"[:'\-]", "_", slug)
    # Replace spaces with underscores
    slug = slug.replace(" ", "_")
    # Remove any double underscores
    slug = re.sub(r"_+", "_", slug)
    # Strip leading/trailing underscores
    slug = slug.strip("_")
    return slug


def classify_document(doc: Dict[str, Any]) -> str:
    """Classify a document by type."""
    content = doc.get("content", "")
    url = doc.get("url", "")
    section_title = doc.get("section_title", "")

    # Skip generic section headers. These are structural headers (Heroes, Fighters, Monsters)
    # used for tracking the current role in enhance_documents() as it iterates through pages
    # in order. They are intentionally excluded from output.
    if section_title.lower() in ['heroes', 'fighters', 'monsters', 'hero', 'fighter', 'monster', 'fighter profiles', 'fighter profile']:
        return "skip"

    # Check for fighter profile: has Move/Toughness/Wounds and section_title looks like a fighter name
    if re.search(r'Move\d+Toughness\d+Wounds\d+', content) and section_title:
        return "fighter_profile"

    # Check for ability: contains [Double], [Triple], etc.
    if any(ability in content for ability in ['[Double]', '[Triple]', '[Quad]', '[Reaction]']):
        return "ability"

    # Check URL patterns
    if '/rules' in url:
        return "rule"
    if '/battleplan' in url:
        return "battleplan"

    return "misc"


def parse_fighter_stats(content: str, section_title: str, page_title: str) -> Dict[str, Any]:
    """Parse fighter stats from content."""
    stats = {}
    weapons = []

    # Parse weapons: pattern like "WeaponNameRangeXAttacksYStrengthZDamage (normal/crit)A/B"
    weapon_pattern = r'([A-Za-z]+)Range(\d+(?:-\d+)?)Attacks(\d+)Strength(\d+)Damage \(normal/crit\)(\d+)/(\d+)'
    weapon_matches = re.findall(weapon_pattern, content)

    for match in weapon_matches:
        name, range_val, attacks, strength, damage_normal, damage_crit = match
        weapons.append({
            "name": name,
            "range": int(range_val) if range_val.isdigit() else range_val,
            "attacks": int(attacks),
            "strength": int(strength),
            "damage_normal": int(damage_normal),
            "damage_crit": int(damage_crit)
        })

    # Parse points: usually a number before Move
    points_match = re.search(r'(\d+)(?=\s*Move)', content)
    if points_match:
        stats["points"] = int(points_match.group(1))

    # Parse faction from page_title
    stats["faction"] = page_title

    # Parse Move/Toughness/Wounds
    move_match = re.search(r'Move(\d+)', content)
    if move_match:
        stats["move"] = int(move_match.group(1))

    toughness_match = re.search(r'Toughness(\d+)', content)
    if toughness_match:
        stats["toughness"] = int(toughness_match.group(1))

    wounds_match = re.search(r'Wounds(\d+)', content)
    if wounds_match:
        stats["wounds"] = int(wounds_match.group(1))

    stats["weapons"] = weapons
    return stats


def clean_content(content: str) -> str:
    """Clean and format content for better readability."""
    content = content.replace('\u200b', ' ')
    # Add spaces before brackets
    content = re.sub(r'(\w)(\[)', r'\1 \2', content)
    # Add spaces after closing brackets
    content = re.sub(r'(\])(\w)', r'\1 \2', content)
    # Add spaces between numbers and letters
    content = re.sub(r'(\d)([A-Z])', r'\1 \2', content)
    # Add spaces between concatenated words (basic)
    content = re.sub(r'([a-z])([A-Z])', r'\1 \2', content)
    return content.strip()


def enhance_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add type and fighter_stats to documents."""
    # Group by page
    pages = defaultdict(list)
    for doc in documents:
        pages[doc["page_title"]].append(doc)
    
    enhanced = []
    for page_title, page_docs in pages.items():
        current_trait = "Fighter"  # default
        for doc in page_docs:
            doc_copy = doc.copy()
            doc_type = classify_document(doc)
            doc_copy["type"] = doc_type

            # Clean content for all docs
            doc_copy["content"] = clean_content(doc["content"])

            # Update current_trait based on section headers
            section_lower = doc["section_title"].lower()
            if section_lower in ["heroes", "hero"]:
                current_trait = "Hero"
            elif section_lower in ["fighters", "fighter"]:
                current_trait = "Fighter"
            elif section_lower in ["monsters", "monster"]:
                current_trait = "Monster"

            if doc_type == "fighter_profile":
                fighter_stats = parse_fighter_stats(doc["content"], doc.get("section_title", ""), doc.get("page_title", ""))
                fighter_stats["role"] = current_trait  # override with current_trait
                doc_copy["fighter_stats"] = fighter_stats

            enhanced.append(doc_copy)
    return enhanced


def write_markdown(chat_path: Path, documents: List[Dict[str, Any]]) -> None:
    """Write documents to a single Markdown file, grouped by page."""
    pages = defaultdict(list)
    for doc in documents:
        pages[doc["page_title"]].append(doc)

    output_lines = ["# Warcry Chat Ready", "", "---", ""]
    for page_title, docs in pages.items():
        output_lines.append(f"## {page_title}")
        output_lines.append("")
        for doc in docs:
            section_title = doc.get("section_title", "")
            doc_type = doc.get("type", "misc")
            if doc_type == "skip":
                continue
            output_lines.append(f"### {section_title}")
            output_lines.append(f"**Type:** {doc_type}")

            if doc_type == "fighter_profile" and "fighter_stats" in doc:
                stats = doc["fighter_stats"]
                output_lines.append(
                    f"**Points:** {stats.get('points','N/A')} | "
                    f"**Role:** {stats.get('role','N/A')} | "
                    f"**Faction:** {stats.get('faction','N/A')} | "
                    f"**Move:** {stats.get('move','N/A')} | "
                    f"**Toughness:** {stats.get('toughness','N/A')} | "
                    f"**Wounds:** {stats.get('wounds','N/A')}"
                )
                output_lines.append("")
                output_lines.append("| Weapon | Range | Attacks | Strength | Damage |")
                output_lines.append("|--------|-------|---------|----------|--------|")
                for weapon in stats.get("weapons", []):
                    output_lines.append(
                        f"| {weapon['name']} | {weapon['range']} | {weapon['attacks']} | {weapon['strength']} | {weapon['damage_normal']}/{weapon['damage_crit']} |"
                    )
            else:
                content = doc.get("content", "").strip()
                if content:
                    output_lines.append(content)

            output_lines.append("---")
        output_lines.append("")

    chat_path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")


def _is_campaign_content(doc: Dict[str, Any]) -> bool:
    """Check if a document is campaign-related content by keyword matching.
    
    Returns True if section_title, page_title, or content contains campaign keywords,
    or if the document is from a named scenario page.
    
    Campaign keywords: quest, background table, aftermath, campaign, lord of the tower,
    campaign arc, glory, renown, roster, encampment, artefact, injury
    """
    section_title = doc.get("section_title", "").lower()
    page_title = doc.get("page_title", "").lower()
    content = doc.get("content", "").lower()
    
    campaign_keywords = [
        "quest", "background table", "aftermath", "campaign", "lord of the tower",
        "campaign arc", "glory", "renown", "roster", "encampment", "artefact", "injury"
    ]
    
    for keyword in campaign_keywords:
        if keyword in section_title or keyword in page_title or keyword in content:
            return True
    
    # Check if this is a named scenario
    scenario_names = [
        "Bloodbaths and Brewgits", "The Grot Purge", "The Royal Hunt", "A Grave Mistake",
        "Thieves in the Night", "Blades in the Darkness", "Thick As Thieves",
        "The Varanite Harvest", "Vault Guardians", "The Rat Hunters", "No Duardin Left Behind",
        "The Forlorn Hope", "The Purge of Anvilgard", "Clash of Might", "The Depths of Sylontum",
        "The Trail of Fire", "Realmshaper Wars", "The Fell Alliance", "The Path of Ven Talax",
        "The Chotec Valley", "War of the Morruk Hills", "The Fall of Lord Valgar",
        "Death Comes Calling", "Trial of the Five Blades", "The Big Carngrad Bash", "Krushed",
        "Gargantuan Carnage", "A Right Old Mess", "Caged Lightning", "Picking Your Poison",
        "Camp Raid", "There Can Be Only One", "A Fool's Trove In Ulfenkarn",
        "Primal Strongholds", "Triumph & Treachery", "Coalition of Death",
        "Warcry Rumble Pack", "Challenge Battles"
    ]
    
    for scenario in scenario_names:
        if scenario.lower() == page_title:
            return True
    
    return False


def _should_drop_document(doc: Dict[str, Any]) -> bool:
    """Check if a document should be dropped entirely from all output files.
    
    Returns True if page_title matches pages that should not be included in any output.
    Dropped pages: Community Resources, Getting Started, Warcry Releases
    """
    page_title = doc.get("page_title", "").lower()
    drop_pages = ["community resources", "getting started", "warcry releases"]
    
    for drop_page in drop_pages:
        if drop_page == page_title:
            return True
    
    return False


def _is_release_content(doc: Dict[str, Any]) -> bool:
    """Check if a document is from the Warcry Releases page.
    
    Returns True if page_title indicates this is release history content.
    """
    page_title = doc.get("page_title", "").lower()
    return "warcry releases" in page_title



def write_combined_fighters_markdown(output_dir: Path, fighter_docs: List[Dict[str, Any]]) -> str:
    """Write all fighter_profile documents into a single output/warcry_fighters.md file."""
    fighters_path = output_dir / "warcry_fighters.md"
    _write_markdown_file(fighters_path, fighter_docs, "Warcry Fighters")
    return str(fighters_path.relative_to(output_dir.parent))


def write_split_markdown(output_dir: Path, documents: List[Dict[str, Any]], combined_fighters: bool = False) -> List[str]:
    """Write documents split into multiple files by type and faction.
    
    Routes documents to:
    - output/warcry_rules.md for core gameplay rules, battleplans, and misc content
    - output/warcry_campaign.md for campaign-related content (scenarios, quests, etc.)
    - output/warcry_releases.md for version release history
    - output/warcry_abilities.md for type "ability"
    - output/factions/<faction_slug>.md for type "fighter_profile" (if not combined_fighters)
    - output/warcry_fighters.md for all fighter_profile (if combined_fighters)
    
    Drops entirely (does not write to any file):
    - Documents from pages: Community Resources, Getting Started, Warcry Releases
    
    Returns a list of file paths written (relative to output_dir).
    """
    # Create output directory structure
    output_dir.mkdir(parents=True, exist_ok=True)
    if not combined_fighters:
        factions_dir = output_dir / "factions"
        factions_dir.mkdir(parents=True, exist_ok=True)
    
    # Organize documents by output file
    core_rules_docs = []  # core gameplay rules
    campaign_docs = []  # campaign-related content
    release_docs = []  # release history
    abilities_docs = []  # ability
    faction_docs = defaultdict(list)  # fighter_profile grouped by faction slug
    
    for doc in documents:
        # Skip documents from pages that should be dropped entirely
        if _should_drop_document(doc):
            continue
        
        doc_type = doc.get("type", "misc")
        
        if doc_type == "skip":
            continue
        elif doc_type in ["misc", "rule", "battleplan"]:
            # Further split misc/rule/battleplan into core rules, campaign, and releases
            if _is_release_content(doc):
                release_docs.append(doc)
            elif _is_campaign_content(doc):
                campaign_docs.append(doc)
            else:
                core_rules_docs.append(doc)
        elif doc_type == "ability":
            abilities_docs.append(doc)
        elif doc_type == "fighter_profile" and "fighter_stats" in doc:
            faction = doc["fighter_stats"].get("faction", "Unknown")
            faction_slug = slugify(faction)
            faction_docs[faction_slug].append(doc)
    
    written_files = []
    
    # Write core rules file
    if core_rules_docs:
        rules_path = output_dir / "warcry_rules.md"
        _write_markdown_file(rules_path, core_rules_docs, "Warcry Rules")
        written_files.append(str(rules_path.relative_to(output_dir.parent)))
    
    # Write campaign file
    if campaign_docs:
        campaign_path = output_dir / "warcry_campaign.md"
        _write_markdown_file(campaign_path, campaign_docs, "Warcry Campaign")
        written_files.append(str(campaign_path.relative_to(output_dir.parent)))
    
    # Write releases file
    if release_docs:
        releases_path = output_dir / "warcry_releases.md"
        _write_markdown_file(releases_path, release_docs, "Warcry Releases")
        written_files.append(str(releases_path.relative_to(output_dir.parent)))
    
    # Write abilities file
    if abilities_docs:
        abilities_path = output_dir / "warcry_abilities.md"
        _write_markdown_file(abilities_path, abilities_docs, "Warcry Abilities")
        written_files.append(str(abilities_path.relative_to(output_dir.parent)))
    
    # Write fighter files
    if combined_fighters:
        all_fighter_docs = []
        for docs in faction_docs.values():
            all_fighter_docs.extend(docs)
        if all_fighter_docs:
            written_files.append(write_combined_fighters_markdown(output_dir, all_fighter_docs))
    else:
        # Write faction files
        for faction_slug, docs in sorted(faction_docs.items()):
            faction_path = factions_dir / f"{faction_slug}.md"
            # Reconstruct faction name from first document for header
            faction_name = docs[0]["fighter_stats"].get("faction", faction_slug)
            _write_markdown_file(faction_path, docs, f"Warcry - {faction_name}")
            written_files.append(str(faction_path.relative_to(output_dir.parent)))
    
    return written_files


def _write_markdown_file(file_path: Path, documents: List[Dict[str, Any]], title: str) -> None:
    """Helper function to write documents to a markdown file with consistent formatting."""
    pages = defaultdict(list)
    for doc in documents:
        pages[doc["page_title"]].append(doc)
    
    output_lines = [f"# {title}", "", "---", ""]
    for page_title, docs in pages.items():
        output_lines.append(f"## {page_title}")
        output_lines.append("")
        for doc in docs:
            section_title = doc.get("section_title", "")
            doc_type = doc.get("type", "misc")
            if doc_type == "skip":
                continue
            output_lines.append(f"### {section_title}")
            output_lines.append(f"**Type:** {doc_type}")
            
            if doc_type == "fighter_profile" and "fighter_stats" in doc:
                stats = doc["fighter_stats"]
                output_lines.append(
                    f"**Points:** {stats.get('points','N/A')} | "
                    f"**Role:** {stats.get('role','N/A')} | "
                    f"**Faction:** {stats.get('faction','N/A')} | "
                    f"**Move:** {stats.get('move','N/A')} | "
                    f"**Toughness:** {stats.get('toughness','N/A')} | "
                    f"**Wounds:** {stats.get('wounds','N/A')}"
                )
                output_lines.append("")
                output_lines.append("| Weapon | Range | Attacks | Strength | Damage |")
                output_lines.append("|--------|-------|---------|----------|--------|")
                for weapon in stats.get("weapons", []):
                    output_lines.append(
                        f"| {weapon['name']} | {weapon['range']} | {weapon['attacks']} | {weapon['strength']} | {weapon['damage_normal']}/{weapon['damage_crit']} |"
                    )
            else:
                content = doc.get("content", "").strip()
                if content:
                    output_lines.append(content)
            
            output_lines.append("---")
        output_lines.append("")
    
    file_path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")



def main() -> None:
    parser = argparse.ArgumentParser(description="Export Warcry crawl to split Markdown files organized by type and faction")
    parser.add_argument("--input", "-i", default="warcry_scrapy_full.json", help="input JSON crawl file")
    parser.add_argument("--output-dir", "-o", default="output", help="output directory for split markdown files (default: output)")
    parser.add_argument("--combined-fighters", action="store_true", default=True, help="combine all fighter profiles into a single file instead of per-faction files")
    parser.add_argument("--no-combined-fighters", action="store_false", dest="combined_fighters", help="split fighter profiles into per-faction files")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")

    print(f"Loading {path}...")
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"Found {len(data)} pages")

    documents = build_documents(data)
    print(f"Built {len(documents)} searchable documents")

    # Enhance documents with type and fighter_stats
    # Note: This processes documents in their original page order before any splitting occurs,
    # preserving role tracking for the enhance_documents() function.
    enhanced_documents = enhance_documents(documents)
    print(f"Enhanced {len(enhanced_documents)} documents with types and stats")

    # Write split markdown files
    output_dir = Path(args.output_dir)
    written_files = write_split_markdown(output_dir, enhanced_documents, args.combined_fighters)
    
    # Print summary
    print(f"\nSummary: Created {len(written_files)} output file(s):")
    for file_path in sorted(written_files):
        print(f"  - {file_path}")
    
    print("Done!")



if __name__ == "__main__":
    main()
