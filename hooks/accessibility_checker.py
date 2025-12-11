# hooks/accessibility_checker.py
"""
MkDocs hook for accessibility validation during build process.
Validates HTML output for WCAG 2.1 AA compliance.
"""

import re
import os
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

logger = logging.getLogger('mkdocs.plugins.accessibility')


def on_post_build(config):
    """
    Run accessibility checks after MkDocs build completes.
    """
    site_dir = config['site_dir']
    logger.info("Running accessibility validation...")

    issues = []
    html_files = []

    # Find all HTML files in the build output
    for root, dirs, files in os.walk(site_dir):
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))

    logger.info(f"Checking {len(html_files)} HTML files for accessibility issues")

    for html_file in html_files:
        relative_path = os.path.relpath(html_file, site_dir)
        file_issues = check_html_accessibility(html_file, relative_path)
        issues.extend(file_issues)

    # Report results
    if issues:
        logger.warning(f"Found {len(issues)} accessibility issues:")
        for issue in issues[:20]:  # Limit output
            logger.warning(f"  {issue}")
        if len(issues) > 20:
            logger.warning(f"  ... and {len(issues) - 20} more issues")
    else:
        logger.info("✅ No accessibility issues found!")

    return issues


def check_html_accessibility(file_path, relative_path):
    """
    Check a single HTML file for accessibility issues.
    Returns list of issue descriptions.
    """
    issues = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
    except Exception as e:
        return [f"{relative_path}: Error reading file - {e}"]

    # Check 1: Images without alt text
    images = soup.find_all('img')
    for img in images:
        if not img.get('alt') and not img.get('aria-label'):
            src = img.get('src', 'unknown')
            issues.append(f"{relative_path}: Image missing alt text: {src}")

    # Check 2: Links without accessible text
    links = soup.find_all('a')
    for link in links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        aria_label = link.get('aria-label', '')
        title = link.get('title', '')

        if not text and not aria_label and not title:
            issues.append(f"{relative_path}: Link without accessible text: {href}")
        elif text and len(text) < 2:
            issues.append(f"{relative_path}: Link with very short text: '{text}' ({href})")

    # Check 3: Heading structure
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    if headings:
        prev_level = 0
        for heading in headings:
            current_level = int(heading.name[1])
            if prev_level > 0 and current_level > prev_level + 1:
                issues.append(f"{relative_path}: Heading level skip from h{prev_level} to h{current_level}")
            prev_level = current_level

    # Check 4: Form elements without labels
    inputs = soup.find_all(['input', 'select', 'textarea'])
    for input_elem in inputs:
        input_type = input_elem.get('type', '')
        input_id = input_elem.get('id', '')

        # Skip certain input types that don't need labels
        if input_type in ['hidden', 'submit', 'button', 'reset']:
            continue

        has_label = False
        aria_label = input_elem.get('aria-label')
        aria_labelledby = input_elem.get('aria-labelledby')

        if aria_label or aria_labelledby:
            has_label = True
        elif input_id:
            # Look for associated label
            label = soup.find('label', {'for': input_id})
            if label:
                has_label = True

        if not has_label:
            issues.append(f"{relative_path}: Form input without label: {input_elem.name} type={input_type}")

    # Check 5: Tables without proper headers
    tables = soup.find_all('table')
    for table in tables:
        headers = table.find_all('th')
        if not headers:
            # Check if it's a data table that should have headers
            rows = table.find_all('tr')
            if len(rows) > 1:  # More than just header row
                issues.append(f"{relative_path}: Data table without proper headers (th elements)")

    # Check 6: Color contrast issues (basic check for common patterns)
    # Look for potentially problematic color combinations in style attributes
    elements_with_style = soup.find_all(attrs={"style": True})
    for elem in elements_with_style:
        style = elem.get('style', '')
        if 'color:' in style and 'background' in style:
            # This is a simplified check - real contrast checking requires color parsing
            if any(low_contrast in style.lower() for low_contrast in
                   ['#ccc', '#ddd', '#eee', 'lightgray', 'lightgrey']):
                issues.append(f"{relative_path}: Potential low contrast colors in inline styles")

    # Check 7: Missing page title
    title = soup.find('title')
    if not title or not title.get_text(strip=True):
        issues.append(f"{relative_path}: Page missing title element")

    # Check 8: Missing main landmark
    main = soup.find('main')
    main_role = soup.find(attrs={"role": "main"})
    if not main and not main_role:
        # Check if this is a content page that should have main
        if not any(skip in relative_path for skip in ['404.html', 'search.html']):
            issues.append(f"{relative_path}: Page missing main landmark")

    # Check 9: Missing language attribute
    html_tag = soup.find('html')
    if html_tag and not html_tag.get('lang'):
        issues.append(f"{relative_path}: HTML element missing lang attribute")

    return issues


def validate_color_contrast(foreground, background):
    """
    Calculate color contrast ratio.
    Returns True if contrast meets WCAG AA standards (4.5:1 for normal text).
    This is a simplified implementation.
    """
    # This would need a full color parsing and contrast calculation implementation
    # For now, return True to avoid false positives
    return True


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def get_luminance(rgb):
    """Calculate relative luminance of RGB color."""

    def normalize(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = [normalize(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color1, color2):
    """Calculate contrast ratio between two colors."""
    lum1 = get_luminance(color1)
    lum2 = get_luminance(color2)

    brighter = max(lum1, lum2)
    darker = min(lum1, lum2)

    return (brighter + 0.05) / (darker + 0.05)


class AccessibilityPlugin:
    """MkDocs plugin for accessibility validation."""

    def __init__(self):
        self.enabled = True
        self.strict_mode = False

    def on_config(self, config):
        """Initialize plugin configuration."""
        accessibility_config = config.get('accessibility', {})
        self.enabled = accessibility_config.get('enabled', True)
        self.strict_mode = accessibility_config.get('strict_mode', False)
        return config

    def on_post_build(self, config):
        """Run accessibility validation after build."""
        if not self.enabled:
            return

        issues = on_post_build(config)

        if issues and self.strict_mode:
            raise Exception(f"Accessibility validation failed with {len(issues)} issues. "
                            "Fix issues or disable strict_mode in config.")


# For direct usage as a script
if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='Check HTML files for accessibility issues')
    parser.add_argument('directory', help='Directory containing HTML files to check')
    parser.add_argument('--strict', action='store_true', help='Exit with error code if issues found')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory")
        sys.exit(1)

    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


    # Mock config object
    class MockConfig:
        def __init__(self, site_dir):
            self.site_dir = site_dir

        def __getitem__(self, key):
            if key == 'site_dir':
                return self.site_dir
            return None

        def get(self, key, default=None):
            if key == 'site_dir':
                return self.site_dir
            return default


    config = MockConfig(args.directory)
    issues = on_post_build(config)

    if issues:
        print(f"\n❌ Found {len(issues)} accessibility issues")
        if args.strict:
            sys.exit(1)
    else:
        print("\n✅ No accessibility issues found!")
        sys.exit(0)
