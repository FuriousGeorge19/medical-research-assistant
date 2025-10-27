#!/usr/bin/env python3
"""
Script to download medical research papers from PubMed Central and other sources.

This script reads paper metadata from medical_papers_metadata.json and downloads
the full-text PDFs to a specified directory.

Usage:
    uv run python download_medical_papers.py [--output-dir DIR] [--delay SECONDS]
"""

import json
import time
import argparse
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing/replacing invalid characters."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # Limit length to 200 characters
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def get_pmc_id_from_pubmed(pubmed_id: str) -> str | None:
    """Try to get PMC ID from PubMed ID using NCBI E-utilities."""
    try:
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pmc&id={pubmed_id}"
        with urlopen(url, timeout=30) as response:
            xml_content = response.read().decode('utf-8')
            root = ET.fromstring(xml_content)

            # Look for PMC ID in the XML response
            for link in root.findall('.//Link'):
                id_elem = link.find('Id')
                if id_elem is not None:
                    return f"PMC{id_elem.text}"

        return None
    except Exception as e:
        print(f"  ⚠️  Could not retrieve PMC ID for PubMed ID {pubmed_id}: {e}")
        return None


def download_pmc_full_text(pmc_id: str, output_path: Path) -> bool:
    """Download full text from PMC using E-utilities (XML format)."""
    try:
        # Remove 'PMC' prefix if present
        pmc_num = pmc_id.replace('PMC', '')

        # Use E-utilities efetch to get full text XML
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc_num}"

        print(f"  📥 Downloading full text from: {url}")

        headers = {'User-Agent': 'Mozilla/5.0'}
        req = Request(url, headers=headers)

        with urlopen(req, timeout=60) as response:
            content = response.read()

            # Save as XML (or TXT if preferred)
            # Change extension to .xml since PMC provides XML
            xml_path = output_path.with_suffix('.xml')
            with open(xml_path, 'wb') as f:
                f.write(content)

        file_size = xml_path.stat().st_size
        if file_size > 5000:  # XML should be reasonably sized
            print(f"  ✅ Downloaded full text XML ({file_size:,} bytes)")
            return True
        else:
            print(f"  ⚠️  Downloaded file seems too small ({file_size} bytes)")
            return False

    except Exception as e:
        print(f"  ❌ Error downloading full text: {e}")
        return False


def download_file(url: str, output_path: Path, paper_title: str) -> bool:
    """Download a file from URL to output_path."""
    try:
        # Add headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = Request(url, headers=headers)

        print(f"  📥 Downloading from: {url}")

        with urlopen(req, timeout=60) as response:
            content = response.read()

            # Check if we actually got a PDF
            if content[:4] != b'%PDF':
                # Check if it's HTML (likely a redirect page)
                if content[:100].lower().find(b'<html') != -1:
                    print(f"  ⚠️  Received HTML instead of PDF (likely redirect page)")
                    return False
                print(f"  ⚠️  Warning: Downloaded content may not be a PDF")

            with open(output_path, 'wb') as f:
                f.write(content)

        file_size = output_path.stat().st_size

        # If file is very small and not a PDF, it's probably an error
        if file_size < 5000 and content[:4] != b'%PDF':
            print(f"  ❌ Downloaded file seems invalid (only {file_size} bytes)")
            output_path.unlink()  # Delete the invalid file
            return False

        print(f"  ✅ Downloaded successfully ({file_size:,} bytes)")
        return True

    except HTTPError as e:
        if e.code == 404:
            print(f"  ❌ PDF not found (404)")
        else:
            print(f"  ❌ HTTP Error {e.code}: {e.reason}")
        return False
    except URLError as e:
        print(f"  ❌ URL Error: {e.reason}")
        return False
    except Exception as e:
        print(f"  ❌ Error downloading: {e}")
        return False


def download_papers(metadata_file: Path, output_dir: Path, delay: float = 1.0):
    """Download papers from metadata file."""

    # Load metadata
    print(f"\n📚 Loading metadata from {metadata_file}")
    with open(metadata_file, 'r') as f:
        data = json.load(f)

    papers = data['papers']
    total = len(papers)
    print(f"   Found {total} papers to download\n")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Track statistics
    stats = {
        'successful': 0,
        'failed': 0,
        'skipped': 0
    }

    failed_papers = []

    # Download each paper
    for idx, paper in enumerate(papers, 1):
        title = paper['title']
        topic = paper['topic']

        print(f"\n[{idx}/{total}] {title}")
        print(f"   Topic: {topic}")

        # Create filename
        safe_title = sanitize_filename(title)
        filename = f"{idx:02d}_{safe_title}.pdf"
        output_path = output_dir / filename

        # Skip if already downloaded
        if output_path.exists():
            print(f"  ⏭️  Already exists, skipping")
            stats['skipped'] += 1
            continue

        # Determine download URL
        pdf_url = None

        if 'pdf_url' in paper:
            pdf_url = paper['pdf_url']
        elif 'pmc_id' in paper:
            pmc_id = paper['pmc_id']
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
        elif 'pubmed_id' in paper:
            # Try to get PMC ID from PubMed ID
            pubmed_id = paper['pubmed_id']
            print(f"  🔍 Looking up PMC ID for PubMed ID: {pubmed_id}")
            pmc_id = get_pmc_id_from_pubmed(pubmed_id)
            if pmc_id:
                print(f"  ✅ Found PMC ID: {pmc_id}")
                pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
            else:
                print(f"  ❌ No PMC ID found, cannot download PDF")
                stats['failed'] += 1
                failed_papers.append({
                    'title': title,
                    'reason': 'No PMC ID available',
                    'url': paper.get('url', 'N/A')
                })
                continue
        elif 'doi' in paper:
            # For DOI papers, use the provided PDF URL if available
            if 'pdf_url' in paper:
                pdf_url = paper['pdf_url']
            else:
                print(f"  ⚠️  DOI paper without PDF URL, trying web URL")
                # Try to construct PDF URL from web URL
                web_url = paper.get('url', '')
                if 'mdpi.com' in web_url:
                    pdf_url = f"{web_url}/pdf"
                elif 'frontiersin.org' in web_url:
                    pdf_url = f"{web_url}/pdf"
                elif 'nature.com' in web_url:
                    pdf_url = f"{web_url}.pdf"

        if not pdf_url:
            print(f"  ❌ Could not determine PDF URL")
            stats['failed'] += 1
            failed_papers.append({
                'title': title,
                'reason': 'No PDF URL available',
                'url': paper.get('url', 'N/A')
            })
            continue

        # Download the file
        success = download_file(pdf_url, output_path, title)

        # If PDF download failed and we have a PMC ID, try downloading full text XML
        if not success and 'pmc_id' in paper:
            print(f"  🔄 Trying alternative: Full text XML download...")
            success = download_pmc_full_text(paper['pmc_id'], output_path)

        if success:
            stats['successful'] += 1
        else:
            stats['failed'] += 1
            failed_papers.append({
                'title': title,
                'reason': 'Download failed',
                'url': pdf_url,
                'manual_url': paper.get('url', 'N/A')
            })

        # Be polite to servers
        if idx < total:
            time.sleep(delay)

    # Print summary
    print("\n" + "="*80)
    print("📊 DOWNLOAD SUMMARY")
    print("="*80)
    print(f"✅ Successfully downloaded: {stats['successful']}")
    print(f"⏭️  Skipped (already exists): {stats['skipped']}")
    print(f"❌ Failed: {stats['failed']}")
    print(f"📁 Output directory: {output_dir.absolute()}")

    if failed_papers:
        print("\n❌ Failed Papers:")
        for i, paper in enumerate(failed_papers, 1):
            print(f"\n{i}. {paper['title']}")
            print(f"   Reason: {paper['reason']}")
            print(f"   URL: {paper['url']}")

        # Save failed papers to a file
        failed_file = output_dir / "failed_downloads.json"
        with open(failed_file, 'w') as f:
            json.dump(failed_papers, f, indent=2)
        print(f"\n💾 Failed papers list saved to: {failed_file}")

    print("\n✨ Download complete!")


def main():
    parser = argparse.ArgumentParser(
        description="Download medical research papers from PubMed Central and other sources"
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('medical_papers'),
        help='Output directory for downloaded papers (default: medical_papers)'
    )
    parser.add_argument(
        '--metadata-file',
        type=Path,
        default=Path('medical_papers_metadata.json'),
        help='Path to metadata JSON file (default: medical_papers_metadata.json)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between downloads in seconds (default: 1.0)'
    )

    args = parser.parse_args()

    # Check if metadata file exists
    if not args.metadata_file.exists():
        print(f"❌ Error: Metadata file not found: {args.metadata_file}")
        print(f"   Please ensure {args.metadata_file} exists in the current directory")
        return 1

    # Download papers
    download_papers(args.metadata_file, args.output_dir, args.delay)
    return 0


if __name__ == '__main__':
    exit(main())
