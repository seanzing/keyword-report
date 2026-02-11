"""HTML template + WeasyPrint PDF generation matching IdealReport.jpeg design."""

from pathlib import Path

from weasyprint import HTML


def _pluralize_industry(industry: str) -> str:
    """Convert industry to customer-friendly plural form."""
    plurals = {
        "plumbing": "plumbers",
        "hvac": "HVAC companies",
        "roofing": "roofers",
        "electrical": "electricians",
        "painting": "painters",
        "landscaping": "landscapers",
        "cleaning": "cleaning services",
        "pest_control": "pest control companies",
    }
    return plurals.get(industry.lower().replace(" ", "_"), f"{industry} businesses")


def _format_number(n: int) -> str:
    """Format number with commas: 1420 -> '1,420'."""
    return f"{n:,}"


def generate_report_pdf(
    business_name: str,
    industry: str,
    keywords: list[dict],
    output_path: Path,
) -> Path:
    """
    Generate a keyword opportunity PDF report.

    Args:
        business_name: Extracted business name
        industry: Business industry
        keywords: List of {"keyword": str, "monthly_searches": int, "on_old_site": bool}
        output_path: Where to save the PDF

    Returns:
        Path to the generated PDF
    """
    industry_plural = _pluralize_industry(industry)
    total_impressions = sum(kw["monthly_searches"] for kw in keywords)
    old_site_count = sum(1 for kw in keywords if kw["on_old_site"])
    new_site_count = len(keywords)

    # Build keyword rows HTML
    keyword_rows = ""
    for kw in keywords:
        impressions = _format_number(kw["monthly_searches"])

        if kw["on_old_site"]:
            old_site_icon = (
                '<span class="check-circle check-yes">'
                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
                '<circle cx="8" cy="8" r="8" fill="#4ecdc4"/>'
                '<path d="M5 8l2 2 4-4" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
                '</svg>'
                '</span>'
            )
        else:
            old_site_icon = (
                '<span class="check-circle check-no">'
                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
                '<circle cx="8" cy="8" r="8" fill="#c5c9d1"/>'
                '<path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="#4a4a5a" stroke-width="1.6" stroke-linecap="round"/>'
                '</svg>'
                '</span>'
            )

        new_site_icon = (
            '<span class="check-circle check-yes">'
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="8" fill="#4ecdc4"/>'
            '<path d="M5 8l2 2 4-4" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
            '</span>'
        )

        keyword_rows += f"""
        <tr class="keyword-row">
            <td class="kw-name">{kw["keyword"]}</td>
            <td class="kw-impressions"><span class="pill">{impressions}/mo</span></td>
            <td class="kw-check">{old_site_icon}</td>
            <td class="kw-check">{new_site_icon}</td>
        </tr>
        """

    # Total row old site display
    if old_site_count > 0:
        old_total_display = f'<span class="total-number">{old_site_count}</span>'
    else:
        old_total_display = f'<span class="total-number">{old_site_count}</span>'

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 30px;
    }}

    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}

    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        background: #f0f2f5;
        color: #1a1a2e;
        -webkit-font-smoothing: antialiased;
    }}

    .container {{
        max-width: 780px;
        margin: 0 auto;
        padding: 20px 0;
    }}

    .card {{
        background: white;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
        padding: 40px;
    }}

    .card-heading {{
        font-size: 22px;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 6px;
    }}

    .card-subtitle {{
        font-size: 14px;
        font-weight: 400;
        color: #6b7280;
        margin-bottom: 28px;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
    }}

    thead th {{
        text-transform: uppercase;
        font-size: 11px;
        font-weight: 600;
        color: #8b95a5;
        letter-spacing: 0.05em;
        padding: 0 12px 12px 12px;
        border-bottom: 1px solid #e8eaed;
    }}

    th.col-keyword {{
        text-align: left;
        width: 42%;
    }}

    th.col-impressions {{
        text-align: center;
        width: 26%;
    }}

    th.col-check {{
        text-align: center;
        width: 16%;
    }}

    .keyword-row td {{
        padding: 14px 12px;
        border-bottom: 1px solid #e8eaed;
        vertical-align: middle;
    }}

    .kw-name {{
        font-size: 15px;
        font-weight: 400;
        color: #1a1a2e;
    }}

    .kw-impressions {{
        text-align: center;
    }}

    .pill {{
        display: inline-block;
        background: #1a3a4a;
        color: white;
        font-size: 13px;
        font-weight: 500;
        padding: 4px 14px;
        border-radius: 20px;
        white-space: nowrap;
    }}

    .kw-check {{
        text-align: center;
    }}

    .check-circle {{
        display: inline-block;
        line-height: 0;
    }}

    /* Total row */
    .total-row td {{
        padding: 16px 12px;
        border-top: 2px solid #d1d5db;
        vertical-align: middle;
    }}

    .total-label {{
        font-size: 15px;
        font-weight: 700;
        color: #1a1a2e;
    }}

    .total-impressions {{
        text-align: center;
    }}

    .pill-total {{
        display: inline-block;
        background: #2ab090;
        color: white;
        font-size: 13px;
        font-weight: 600;
        padding: 4px 14px;
        border-radius: 20px;
        white-space: nowrap;
    }}

    .total-check {{
        text-align: center;
    }}

    .total-number {{
        font-size: 15px;
        font-weight: 400;
        color: #8b95a5;
    }}

    .total-new {{
        font-size: 15px;
        font-weight: 700;
        color: #4ecdc4;
    }}

    /* Bottom banner */
    .banner {{
        background: linear-gradient(135deg, #1a1a2e 0%, #2a2a4e 100%);
        border-radius: 12px;
        margin-top: 30px;
        padding: 32px 40px;
        text-align: center;
    }}

    .banner-heading {{
        font-size: 20px;
        font-weight: 700;
        color: white;
        margin-bottom: 12px;
    }}

    .banner-text {{
        font-size: 14px;
        font-weight: 400;
        color: rgba(255,255,255,0.85);
        line-height: 1.6;
        max-width: 580px;
        margin: 0 auto;
    }}

    /* Footer */
    .footer {{
        text-align: center;
        margin-top: 20px;
        font-size: 12px;
        color: #9ca3af;
    }}
</style>
</head>
<body>
<div class="container">
    <div class="card">
        <div class="card-heading">Your Keywords</div>
        <div class="card-subtitle">These are the search terms your customers use to find {industry_plural} in your area</div>

        <table>
            <thead>
                <tr>
                    <th class="col-keyword">Keyword</th>
                    <th class="col-impressions">Monthly Impressions</th>
                    <th class="col-check">Old Site</th>
                    <th class="col-check">New Site</th>
                </tr>
            </thead>
            <tbody>
                {keyword_rows}
                <tr class="total-row">
                    <td class="total-label">Total (showing {new_site_count} of 50 keywords)</td>
                    <td class="total-impressions"><span class="pill-total">{_format_number(total_impressions)}/mo</span></td>
                    <td class="total-check">{old_total_display}</td>
                    <td class="total-check"><span class="total-new">{new_site_count}</span></td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="banner">
        <div class="banner-heading">What this means for {business_name}</div>
        <div class="banner-text">
            With your new website and 50 landing pages, your business has the potential to appear
            in thousands more local searches every month. More visibility means more enquiries,
            and more enquiries means more jobs.
        </div>
    </div>

    <div class="footer">
        Prepared by ZING Website Design &middot; zing.work
    </div>
</div>
</body>
</html>"""

    # Generate PDF
    output_path = Path(output_path)
    HTML(string=html_content).write_pdf(str(output_path))

    return output_path
