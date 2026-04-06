#!/usr/bin/env python3
"""Export Scrapy crawl output to a single Markdown file for ChatGPT."""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List
from collections import defaultdict

import sys
sys.path.insert(0, str(Path(__file__).parent))
from search import build_documents


def classify_document(doc: Dict[str, Any]) -> str:
    """Classify a document by type."""
    content = doc.get("content", "")
    url = doc.get("url", "")
    section_title = doc.get("section_title", "")

    # Skip generic section headers
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


def write_text(chat_path: Path, documents: List[Dict[str, Any]]) -> None:
    """Write documents to a plain text file."""
    pages = defaultdict(list)
    for doc in documents:
        pages[doc["page_title"]].append(doc)

    output_lines = ["Warcry Chat Ready", "", "===", ""]
    for page_title, docs in pages.items():
        output_lines.append(f"{page_title.upper()}")
        output_lines.append("")
        for doc in docs:
            section_title = doc.get("section_title", "")
            doc_type = doc.get("type", "misc")
            if doc_type == "skip":
                continue
            output_lines.append(f"{section_title}")
            output_lines.append(f"Type: {doc_type}")

            if doc_type == "fighter_profile" and "fighter_stats" in doc:
                stats = doc["fighter_stats"]
                output_lines.append(f"Role: {stats.get('role', 'Fighter')}")
                output_lines.append(f"Points: {stats.get('points', 'N/A')}")
                output_lines.append(f"Faction: {stats.get('faction', 'N/A')}")
                output_lines.append(f"Move: {stats.get('move', 'N/A')}")
                output_lines.append(f"Toughness: {stats.get('toughness', 'N/A')}")
                output_lines.append(f"Wounds: {stats.get('wounds', 'N/A')}")
                output_lines.append("Weapons:")
                for weapon in stats.get("weapons", []):
                    output_lines.append(f"- {weapon['name']}: Range {weapon['range']}, Attacks {weapon['attacks']}, Strength {weapon['strength']}, Damage {weapon['damage_normal']}/{weapon['damage_crit']}")
            else:
                content = doc.get("content", "").strip()
                if content:
                    output_lines.append(content)

            output_lines.append("===")
        output_lines.append("")

    text_content = "\n".join(output_lines).rstrip() + "\n"
    chat_path.write_text(text_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Warcry crawl to a single Markdown file for ChatGPT")
    parser.add_argument("--input", "-i", default="warcry_scrapy_full.json", help="input JSON crawl file")
    parser.add_argument("--chat-ready", default="warcry_chat_ready.txt", help="output ChatGPT-friendly file")
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
    enhanced_documents = enhance_documents(documents)
    print(f"Enhanced {len(enhanced_documents)} documents with types and stats")

    # Write Markdown format (both .txt and .md)
    chat_path = Path(args.chat_ready)
    write_markdown(chat_path, enhanced_documents)
    print(f"Wrote Markdown format to {chat_path}")
    
    # Also output as .md file
    md_path = Path(str(chat_path).replace(".txt", ".md"))
    write_markdown(md_path, enhanced_documents)
    print(f"Wrote Markdown format to {md_path}")
    
    # Write text format
    text_path = Path(str(chat_path).replace(".txt", "_text.txt"))
    write_text(text_path, enhanced_documents)
    print(f"Wrote text format to {text_path}")

    print("Done!")


if __name__ == "__main__":
    main()
